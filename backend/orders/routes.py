
from datetime import timedelta
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.config.settings import config_settings
from backend.common.utils import now
from backend.db.dependencies import get_session
from backend.orders.constants import RESERVATION_TTL_MINUTES
from backend.orders.repository import capture_cart_snapshot, compute_final_total, get_checkout_details, get_or_create_checkout_session, order_totals_n_checkout_method_updates, place_order_with_items, reserve_inventory, spc_by_ikey, validate_checkout_get_items_paymethod
from backend.orders.services import create_payment_intent, validate_items_avblty
from backend.schema.full_schema import Payment


orders_router=APIRouter()


# in cart (user clicks on procceed to buy)
@orders_router.post("/checkout/initiate")
async def initiate_buy_now(request:Request,
    session: AsyncSession = Depends(get_session)):

    user_identifier=request.state.user_identifier
    reserved_until = now() + timedelta(minutes=RESERVATION_TTL_MINUTES)
   
    cart_data = await capture_cart_snapshot(session, user_identifier)
    cart_items=cart_data["items"]
    
    checkout_public_id = await get_or_create_checkout_session(session,user_identifier,cart_data["cart_id"],cart_items,reserved_until)
    return {
        "checkout_id": checkout_public_id
    }


# client should get the checkout id recived from initiate_buy_now ,store it and set it in url 
# ask to user for payment options in ui , users can select payment methods 
# most probably items won't run out of stock until payment second step so do reservation at 2nd level here

# when user clicks on proceed with selected payment method 
#** can use a checkout status to return early for dobule requests to reduce latency 
@orders_router.post("/checkout/{checkout_id}/order-summary")
async def get_order_summary(request:Request,checkout_id: str,
    payload: Dict[str, Any],
    session: AsyncSession = Depends(get_session),):
    """
    POST /checkout/{checkout_id}/select-method
    Body: { "payment_method": "UPI"|"COD" }
    Holds reservations and computes totals with payment-method adjustments.
    Returns server-validated order summary. Does NOT create final Order.
    """
    user_identifier=request.state.user_identifier
    payment_method = payload.get("payment_method")
    if payment_method not in ("UPI", "COD"):
        raise HTTPException(status_code=400, detail="payment_method must be UPI or COD")
    
    cs=await get_checkout_details(session,checkout_id,user_identifier)
    cart_items=cs["cs_cart_snap"]["items"]
    print("cart_items",cart_items)
    print(type(cart_items))
    
    # Validate availability for each item , 
    # err is raised even if non avblty for 1 item , in case want to allow avbl items tp proceed through return valid items from validate_items_avblty
    await validate_items_avblty(session,cart_items)
    await reserve_inventory(session,cart_items,cs["cs_id"],cs["cs_expires_at"])
    res=await order_totals_n_checkout_method_updates(session,cart_items,payment_method,cs["cs_id"],checkout_id,cs["cs_expires_at"])
    await session.commit()  
    # commit inv reservation and payment method update under a single commit 
    # so that if network fails for long time before checkout update it may give some other user's concurrent request to proceed through in case of low stock
    # otherwise inventory will stay on hold because of this midway failed request .
    # or commit seprately as well it is concurrent safe in the way that it won't cause bad states .

    return res

# when clicked on proceed to pay with upi etc. call this 
# order creation will happen here in final stage
#** also store a request hash of items data for full enhanced security 
@orders_router.post("/checkout/{checkout_id}/secure-confirm")
async def place_order(request:Request,checkout_id: str,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session)):

    user_identifier=request.state.user_identifier
    
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required for order confirm")
    # validate if checkout session is still active 
    items,payment_method = await validate_checkout_get_items_paymethod(session,checkout_id,user_identifier)  
    
    order_npay_data = await spc_by_ikey(session,idempotency_key,user_identifier)
    if order_npay_data and order_npay_data["response_body"] is not None:
        return order_npay_data
    
    order_totals=compute_final_total(items,payment_method)

    order_data = await place_order_with_items(session,user_identifier,payment_method,order_totals,idempotency_key)
    await session.commit()  # commit order ,orderitems ,record payment init pending state for pay now and idempotency record atomically 
    
    #** update product stock and stuff via bg workers , emit order place event . Also remove items from cart .

    pay_public_id=order_data.get("pay_public_id",None)

    print("pay_public_id",pay_public_id)

    if pay_public_id:
        order_pay_res=await create_payment_intent(session,idempotency_key,order_totals,order_data)
        return order_pay_res
    
    return order_data
        

    
# ----------------------------------------------------------------------------------------------------
# for testing of upi app simulation 
from fastapi.responses import HTMLResponse

TEST_HTML_TEMPLATE = """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Razorpay Checkout Test</title>
  <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
</head>
<body>
  <h3>Razorpay Checkout Test</h3>
  <p>Order: <strong id="ord"></strong></p>
  <p>Amount (paise): <strong id="amt"></strong></p>
  <button id="pay">Open Checkout</button>
  <script>
    const KEY = "{{KEY}}";
    const ORDER_ID = "{{ORDER_ID}}";
    const AMT = {{AMOUNT}};
    document.getElementById("ord").textContent = ORDER_ID;
    document.getElementById("amt").textContent = AMT;

    document.getElementById("pay").addEventListener("click", function () {
      const options = {
        key: KEY,
        order_id: ORDER_ID,
        amount: AMT,
        name: "Phyllonix (Test)",
        description: "Test order",
        prefill: { name: "Test User", email: "test@example.com" },
        handler: function (response) {
          alert("Checkout handler: " + JSON.stringify(response));
        }
      };
      const rzp = new Razorpay(options);
      rzp.open();
    });
  </script>
</body>
</html>
"""

@orders_router.get("/test/checkout/{order_public_id}", response_class=HTMLResponse)
async def serve_test_checkout(request: Request, order_public_id: str, auth_token : str ,session = Depends(get_session)):
    # 1) Ensure user is authenticated (or adjust logic if admin/testing)
    # user_id = getattr(request.state, "user_identifier", None)
    # if not user_id:
    #     # if you want to allow local dev without auth, you can skip this check
    #     raise HTTPException(status_code=401, detail="login required to open test checkout")

    # 2) load provider order id and amount from DB by order_public_id
    async with session as s:
        stmt = select(Payment.provider_payment_id, Payment.amount, Payment.currency).where(Payment.provider_payment_id == order_public_id).limit(1)
        res = await s.execute(stmt)
        row = res.one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="payment/order not found")
        provider_payment_id, amount, currency = row

    if not provider_payment_id:
        raise HTTPException(status_code=400, detail="provider_payment_id missing; create payment intent first")

    # 3) get Razorpay public key from config/env
    RAZORPAY_KEY_ID =  config_settings.RZPAY_KEY # or read from env/config

    # 4) render HTML with values injected
    html = TEST_HTML_TEMPLATE.replace("{{KEY}}", RAZORPAY_KEY_ID).replace("{{ORDER_ID}}", provider_payment_id).replace("{{AMOUNT}}", str(int(amount)))
    return HTMLResponse(html)

    


        
    


# ----------------------------------------------------------------------------------------------------
# after payment success payment provider api will send a webhook to our server 
# -- next in webhooks file
# ----------------------------------------------------------------------------------------------------

# @orders_router.get()
# async def get_all_orders():
#     pass




