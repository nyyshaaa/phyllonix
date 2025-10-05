

from datetime import timedelta
from typing import Any, Dict
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.utils import now
from backend.db.dependencies import get_session
from backend.orders.constants import RESERVATION_TTL_MINUTES
from backend.orders.repository import create_checkout_session, get_checkout_session, load_cart_items, validate_items_avblty


orders_router=APIRouter()


# in cart (user clicks on procceed to buy)
@orders_router.post("/checkout/initiate")
async def initiate_buy_now(request:Request, payload: Dict[str, Any],
    session: AsyncSession = Depends(get_session)):

    user_identifier=request.state.user_identifier

    await get_checkout_session(session,user_identifier)

    cart_data = await load_cart_items(session, user_identifier)
    cart_items=cart_data["cart_items"]
    
    # Validate availability for each item
    validate_items_avblty(session,cart_items)

    reserved_until = now() + timedelta(minutes=RESERVATION_TTL_MINUTES)
    checkout_public_id = await create_checkout_session(session,user_identifier,cart_data["cart_id"],cart_items)
    
    return {
        "checkout_id": checkout_public_id,
        "expires_at": reserved_until.isoformat()
    }


# client should get the checkout id recived from initiate_buy_now ,store it and set it in url 
# ask to user for payment options in ui , users can select payment methods 

# when user clicks on proceed with selected payment method 
@orders_router.get("/checkout/{checkout_id}/order-summary")
async def get_order_summary(checkout_id:str):
    pass


# when clicked on proceed to pay with upi etc. call this 
# order creation will happen here in final stage
@orders_router.get("/{checkout_id}/secure-payment-init")
async def place_order_with_pay(checkout_id:str):
    pass

# ----------------------------------------------------------------------------------------------------
# after payment success payment provider api will send a webhook to our server 
# -- next in webhooks file
# ----------------------------------------------------------------------------------------------------

@orders_router.get()
async def get_all_orders():
    pass




