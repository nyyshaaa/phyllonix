


from datetime import timedelta
from typing import Any, Dict, List

from fastapi import HTTPException,status
from sqlalchemy import func, select, text

from backend.common.utils import now
from backend.orders.constants import RESERVATION_TTL_MINUTES
from backend.schema.full_schema import Cart, CartItem, CheckoutSession, InventoryReservation, InventoryReserveStatus, Product


async def load_cart_items(session, user_id: int) -> List[Dict[str, Any]]:
    
    stmt = (
        select(Cart.id,CartItem.id, CartItem.product_id, CartItem.quantity, Product.base_price , Product.stock_qty)
        .join(Cart,Cart.id==CartItem.cart_id)
        .join(Product, Product.id == CartItem.product_id)
        .where(Cart.user_id == user_id)
    )
    res = await session.execute(stmt)
    rows = res.all()
    first = rows[0]
    cart_id = first.cart_id
    if cart_id is None :
        raise HTTPException()
        
    items = []
    for r in rows:
        cid, pid, qty, base_price, pr_qty = r
        items.append({
            "cart_item_id": int(cid),
            "product_id": int(pid),
            "quantity": int(qty),
            "prod_base_price": int(base_price),
            "product_stock": pr_qty,
        })
    return {
        "cart_id":cart_id,
        "items":items
    }


async def product_avblty(session, product_id, product_stock_qty: int) -> int:
    """Return available = stock_qty - sum(active reservations)."""
   
    # sum of active reservations
    stmt2 = select(func.coalesce(func.sum(InventoryReservation.quantity), 0)).where(
        InventoryReservation.product_id == product_id,
        InventoryReservation.status == "ACTIVE",
        InventoryReservation.reserved_until > now(),
    )
    res2 = await session.execute(stmt2)
    reserved_sum = int(res2.scalar_one() or 0)

    return max(0, product_stock_qty - reserved_sum)

async def validate_items_avblty(session,cart_items):
    item_errs=[]
    for it in cart_items:
        available = await product_avblty(session, it["product_id"],it["product_stock"])
        if it["quantity"] > available:
            item_errs.append({"detail":f"Not enough stock for product_id={it['product_id']}. requested={it['quantity']} available={available}"})

    if len(item_errs) != 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,detail=f"There is problem with some items stock qty {item_errs}")
    

# create checkout session and resrver inventory atomically 
async def create_checkout_session(session,user_id,cart_id,items,reserved_until):
   
    cs = CheckoutSession(
        user_id=user_id,
        cart_snapshot={"cart_id": cart_id, "items": items},
        expires_at=reserved_until,
        selected_payment_method=None
    )
    session.add(cs)
    await session.flush()  # get cs.id

    cs_id = cs.id
    cs_public_id = cs.public_id

    await reserve_inventory(session,items,cs_id,reserved_until)

    await session.commit()

    return cs_public_id


async def reserve_inventory(session,cart_items,cs_id,reserved_until):
    for it in cart_items:
        inv = InventoryReservation(
            product_id=it["product_id"],
            checkout_session_id=cs_id,
            quantity=it["quantity"],
            reserved_until=reserved_until,
            status=InventoryReserveStatus.ACTIVE.value
        )
        session.add(inv)


async def get_checkout_session(session,user_id):
  
    # Reuse active checkout session if exists
    stmt = select(CheckoutSession).where(
        CheckoutSession.user_id == user_id,
        CheckoutSession.expires_at > now()
    ).limit(1)
    res = await session.execute(stmt)
    cs = res.scalar_one_or_none()
    if cs:  
        return {
            "checkout_id": cs.public_id,
            "expires_at": cs.expires_at.isoformat() if cs.expires_at else None,
        }