
import asyncio
from datetime import timedelta
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Request , status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.auth.utils import decode_token
from backend.config.settings import config_settings
from backend.common.utils import build_success, json_ok, now
from backend.db.dependencies import get_session
from backend.orders.constants import RESERVATION_TTL_MINUTES
from backend.orders.repository import capture_cart_snapshot, compute_final_total, get_checkout_details, get_or_create_checkout_session, if_cart_exists, place_order_with_items, record_order_idempotency, remove_items_from_cart, reserve_inventory, short_circuit_concurrent_req, spc_by_ikey, update_checkout_activeness, update_checkout_cart_n_paymethod, validate_checkout_get_items_paymethod
from backend.orders.services import create_payment_intent, validate_items_avblty
from backend.orders.utils import acquire_pglock, compute_order_totals, idempotency_lock_key
from backend.schema.full_schema import Orders, Payment
from backend.config.admin_config import admin_config
from backend.user.repository import identify_user_by_pid

current_env = admin_config.ENV


orders_router=APIRouter()


# in cart (user clicks on procceed to buy)
@orders_router.post("/checkout/initiate")
async def initiate_buy_now(request:Request,
    session: AsyncSession = Depends(get_session)):

    user_identifier=request.state.user_identifier
    reserved_until = now() + timedelta(minutes=RESERVATION_TTL_MINUTES)

    await if_cart_exists(session,user_identifier)

    checkout_public_id = await get_or_create_checkout_session(session, user_identifier, reserved_until)
    await session.commit()
    data = {
        "checkout_id": str(checkout_public_id),
        "reserved_until": str(reserved_until),
    }
    payload = build_success(data, trace_id=None)
    return json_ok(payload, status_code=status.HTTP_201_CREATED)


# client should get the checkout id recived from initiate_buy_now ,store it and set it in url 
# ask to user for payment options in ui , users can select payment methods 
# most certainly items won't run out of stock until payment second step so do reservation at 2nd level here and to prevent extra work if user leaving mid steps

# when user clicks on proceed with selected payment method 
@orders_router.post("/checkout/{checkout_id}/order-summary")
async def get_order_summary(request:Request,checkout_id: str,
    payload: Dict[str, Any],
    session: AsyncSession = Depends(get_session)):
   
    user_identifier=request.state.user_identifier

    payment_method = payload.get("payment_method")
    if payment_method not in ("UPI", "COD"):
        raise HTTPException(status_code=400, detail="payment_method must be UPI or COD")
    
    cs=await get_checkout_details(session,checkout_id,user_identifier)

    items = cs["cs_cart_snap"].get("items", []) if cs["cs_cart_snap"] else None
    pay_method=cs["cs_pay_method"]

    if items and pay_method:
        res=compute_order_totals(items,pay_method,checkout_id,cs["cs_expires_at"])
        payload = build_success(res, trace_id=None)
        return json_ok(payload)
    
    # take locks on product rows to get a direct xclusive lock 
    cart_data = await capture_cart_snapshot(session, user_identifier)
    cart_items = cart_data["items"]

    # Validate availability for each item , 
    # err is raised even if non avblty for 1 item , in case want to allow avbl items tp proceed through return valid items from validate_items_avblty
    await validate_items_avblty(session,cart_items)

    await reserve_inventory(session,cart_items,cs["cs_id"],cs["cs_expires_at"])
    await update_checkout_cart_n_paymethod(session,cs["cs_id"],payment_method,cart_items)
    await session.commit()  
   
    res=compute_order_totals(cart_items,payment_method,checkout_id,cs["cs_expires_at"])

    payload = build_success(res, trace_id=None)
    return json_ok(payload)
    # commit inv reservation and payment method update under a single commit 
    # so that if network fails for long time before checkout update it may give some other user's concurrent request to proceed through in case of low stock
    # otherwise inventory will stay on hold because of this midway failed request .
    # or commit seprately as well it is concurrent safe in the way that it won't cause bad states .


# when clicked on proceed to pay with upi etc or just for creating order with pay later option. call this 
# order creation will happen here in final stage
#** also store a request hash of items data for full enhanced security (send it from frontend side to identify requests along with idempotency)
@orders_router.post("/checkout/{checkout_id}/secure-confirm")
async def place_order(request:Request,checkout_id: str,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session)):

    user_identifier=request.state.user_identifier
    
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required for order confirm")
    
    # validate if checkout session is still active 
    cs_id,items,payment_method = await validate_checkout_get_items_paymethod(session,checkout_id,user_identifier)
  
    lock_key = idempotency_lock_key(idempotency_key)
    # Try to acquire advisory lock (non-blocking)
    got_lock = await acquire_pglock(session,lock_key)

    # for now let the concurrent requests wait as we acquired ikey lock initially only ,
    #  instead of short circuit and when they acquire lock they can just return existing response data for ikey .
    # if not got_lock:
    #     return await short_circuit_concurrent_req(session,idempotency_key,
    #                  user_identifier,checkout_id)
    
    order_data_by_ik = await spc_by_ikey(session,idempotency_key,user_identifier)

    ik_id = None

    if order_data_by_ik is not None:
        if order_data_by_ik["cs_id"] != cs_id:
            raise HTTPException(status_code=400, detail="Unauthorized checkout session for provided idempotency key")
    
        if order_data_by_ik["response_body"] is not None:
            ik_id = order_data_by_ik["ik_id"]
            payload = build_success(order_data_by_ik, trace_id=None)
            return json_ok(payload)
    
    if not ik_id: 
        ik_id=await record_order_idempotency(session,idempotency_key,user_identifier)

        # code path may happen in case of concurrent requests, if somehow lock wasn't acquired by any request
        #** better to short circuit here and send status url direction to client 
        if not ik_id :
            print("concurrent")
            await asyncio.sleep(5)

            order_data_by_ik = await spc_by_ikey(session,idempotency_key,user_identifier)
            if order_data_by_ik and order_data_by_ik["response_body"] is not None:
                payload = build_success(order_data_by_ik, trace_id=None)
                return json_ok(payload)
            ik_id = order_data_by_ik["ik_id"]
    
    #** should short circuit here for concurrent requests(or retries) instead of allowing to proceed through . 
    # and if client receives that shortcircuited response due to timing of requests it can poll status .

    order_totals=compute_final_total(items,payment_method)
    
    order_resp_data = await place_order_with_items(session,user_identifier,
                                              payment_method,order_totals,ik_id)
    #**may emit an event to remove cart items in async way in prod
    # await remove_items_from_cart(session,items)

    await session.commit()  # commit order ,orderitems ,record payment init pending state for pay now and idempotency record atomically 

    pay_public_id=order_resp_data.get("pay_public_id",None)

    if pay_public_id:
        order_pay_res=await create_payment_intent(session,idempotency_key,order_totals,order_resp_data)
        await update_checkout_activeness(session,cs_id)
        return order_pay_res
    
    payload = build_success(order_resp_data, trace_id=None)
    return json_ok(payload)


        

    
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

@orders_router.get("/checkout/{provider_order_public_id}/secure-process", response_class=HTMLResponse)
async def serve_checkout(request: Request, provider_order_public_id: str, session = Depends(get_session)):
    user_identifier=request.state.user_identifier
    
    async with session as s:
        stmt = (
                    select(Payment.provider_order_id, Payment.amount, Payment.currency, Orders.user_id)
                    .join(Orders, Payment.order_id == Orders.id)
                    .where(Payment.provider_order_id == provider_order_public_id)
                )
        res = await s.execute(stmt)
        row = res.one_or_none()
        if row is None:
            #** add for reconcilation (delete earlier pending payment rows ) as it cannot be attempted without valid record
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="payment record not found for provided provider public order id ")
        provider_order_id, amount, currency ,order_user_id= row

    if order_user_id is None or user_identifier != order_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorizes user")

    RAZORPAY_KEY_ID =  config_settings.RZPAY_KEY

    html = TEST_HTML_TEMPLATE.replace("{{KEY}}", RAZORPAY_KEY_ID).replace("{{ORDER_ID}}", provider_order_id).replace("{{AMOUNT}}", str(int(amount)))
    return HTMLResponse(html)


    
# only in dev and staging test mode 
async def test_checkout_upi_app_sim(request: Request, provider_order_public_id: str,auth_token:str ,session = Depends(get_session)):
   
    decoded_token=decode_token(auth_token)
    if not decoded_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Invalid or expired token provided.")
    
    user_pid = decoded_token.get("sub")
    user_identifier=await identify_user_by_pid(session,user_pid)

    async with session as s:
        stmt = (
                    select(Payment.provider_order_id, Payment.amount, Payment.currency, Orders.user_id)
                    .join(Orders, Payment.order_id == Orders.id)
                    .where(Payment.provider_order_id == provider_order_public_id)
                )
        res = await s.execute(stmt)
        row = res.one_or_none()
        if row is None:
            #** add for reconcilation (delete earlier pending payment rows ) as it cannot be attempted without valid record
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="payment record not found for provided provider public order id ")
        provider_order_id, amount, currency ,order_user_id= row

    if order_user_id is None or user_identifier != order_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorizes user")

    RAZORPAY_KEY_ID =  config_settings.RZPAY_KEY

    html = TEST_HTML_TEMPLATE.replace("{{KEY}}", RAZORPAY_KEY_ID).replace("{{ORDER_ID}}", provider_order_id).replace("{{AMOUNT}}", str(int(amount)))
    return HTMLResponse(html)

    
if current_env == "dev" or current_env == "staging":
    orders_router.add_api_route("/checkout/test/{provider_order_public_id}",
                                test_checkout_upi_app_sim,methods=["GET"],name="UPI_APP_TEST_CHECKOUT",dependencies=[Depends(get_session)],
                                response_class=HTMLResponse)

