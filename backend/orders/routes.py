

from datetime import timedelta
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.utils import now
from backend.db.dependencies import get_session
from backend.orders.constants import RESERVATION_TTL_MINUTES
from backend.orders.repository import capture_cart_snapshot, create_checkout_session, get_checkout_details, get_checkout_session, order_totals_n_checkout_updates, place_order_with_items, reserve_inventory, spc_by_ikey, validate_checkout_nget_totals
from backend.orders.services import create_payment_intent, validate_items_avblty


orders_router=APIRouter()


# in cart (user clicks on procceed to buy)
#**(done) create an index on user id and status of checkout for idempotency of /checkout/initiate or send i key 
@orders_router.post("/checkout/initiate")
async def initiate_buy_now(request:Request,
    session: AsyncSession = Depends(get_session)):

    user_identifier=request.state.user_identifier

    checkout_public_id = await get_checkout_session(session,user_identifier)

    if checkout_public_id is None :
        cart_data = await capture_cart_snapshot(session, user_identifier)
        cart_items=cart_data["cart_items"]
        reserved_until = now() + timedelta(minutes=RESERVATION_TTL_MINUTES)

        checkout_public_id = await create_checkout_session(session,user_identifier,cart_data["cart_id"],cart_items,reserved_until)
    
    return {
        "checkout_id": checkout_public_id
    }


# client should get the checkout id recived from initiate_buy_now ,store it and set it in url 
# ask to user for payment options in ui , users can select payment methods 
# most probably items won't run out of stock until payment second step so do reservation at 2nd level here

# when user clicks on proceed with selected payment method 
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
    cart_items=cs["cs_cart_snap"]
    
    # Validate availability for each item
    await validate_items_avblty(session,cart_items)
    await reserve_inventory(session,cart_items,cs["cs_id"],cs["cs_expires_at"])
    res=await order_totals_n_checkout_updates(session,cart_items,payment_method,cs["cs_id"],checkout_id,cs["cs_expires_at"])
    await session.commit()

    return res

# when clicked on proceed to pay with upi etc. call this 
# order creation will happen here in final stage
@orders_router.post("checkout/{checkout_id}/secure-confirm")
async def place_order(request:Request,checkout_id: str,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session)):

    user_identifier=request.state.user_identifier
    
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required for confirm")
    
    order_npay_data = await spc_by_ikey(session,idempotency_key)

    if order_npay_data:
        return order_npay_data

    order_totals,payment_method = await validate_checkout_nget_totals(session,checkout_id)
    order_data = await place_order_with_items(session,user_identifier,payment_method,order_totals,idempotency_key)
    
    pay_public_id=order_data.get("pay_public_id",None)

    if pay_public_id:
        order_pay_res=create_payment_intent(session,idempotency_key,order_totals,order_data)
        return order_pay_res
    
    return order_data
        

    
    


        
    


# ----------------------------------------------------------------------------------------------------
# after payment success payment provider api will send a webhook to our server 
# -- next in webhooks file
# ----------------------------------------------------------------------------------------------------

@orders_router.get()
async def get_all_orders():
    pass




