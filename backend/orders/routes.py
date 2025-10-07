

from datetime import timedelta
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.utils import now
from backend.db.dependencies import get_session
from backend.orders.constants import RESERVATION_TTL_MINUTES
from backend.orders.repository import compute_order_totals, create_checkout_session, get_checkout_details, get_checkout_session, load_cart_items, reserve_inventory, spc_by_ikey, validate_checkout
from backend.orders.services import validate_items_avblty


orders_router=APIRouter()


# in cart (user clicks on procceed to buy)
#** create an index on user id and status of checkout for idempotency of /checkout/initiate or send i key 
@orders_router.post("/checkout/initiate")
async def initiate_buy_now(request:Request,
    session: AsyncSession = Depends(get_session)):

    user_identifier=request.state.user_identifier

    await get_checkout_session(session,user_identifier)

    cart_data = await load_cart_items(session, user_identifier)
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
@orders_router.get("/checkout/{checkout_id}/order-summary")
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
    cart_items=cs.cart_items
    
    # Validate availability for each item
    await validate_items_avblty(session,cart_items)
    await reserve_inventory(session,cart_items,cs.id,cs.expires_at)
    res=await compute_order_totals(session,cart_items,payment_method,cs.id,checkout_id,cs.expires_at)
    
    return res

# when clicked on proceed to pay with upi etc. call this 
# order creation will happen here in final stage
@orders_router.get("checkout/{checkout_id}/secure-confirm")
async def place_order_with_pay(request:Request,checkout_id: str,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session)):
    
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required for confirm")
    
    order_npay_data = await spc_by_ikey(session,idempotency_key)

    await validate_checkout(session,checkout_id)
    


# ----------------------------------------------------------------------------------------------------
# after payment success payment provider api will send a webhook to our server 
# -- next in webhooks file
# ----------------------------------------------------------------------------------------------------

@orders_router.get()
async def get_all_orders():
    pass




