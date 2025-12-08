
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.cart.repository import add_item_to_cart, get_or_create_cart, get_product_data
from backend.common.utils import success_response
from backend.db.dependencies import get_session

carts_router=APIRouter()

@carts_router.post("/items/{product_public_id}")
async def add_to_cart(request:Request,product_public_id:str,session:AsyncSession=Depends(get_session)):
    user_id = getattr(request.state, "user_identifier", None)
    sid = getattr(request.state, "sid", None)

    product_data=await get_product_data(session,product_public_id)

    cart_id = await get_or_create_cart(session,user_id,sid)

    if not cart_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Cart could not be created")
    
    cart_item, created = await add_item_to_cart(session, cart_id, product_data)

    resp =  {
        "cart_id": cart_id,
        "item": {
            "id": cart_item["id"],
            "product_id": product_data["id"],
            "quantity": cart_item["quantity"],
            "created": created,
        },
    }


    response = success_response(resp, 200)
    return response