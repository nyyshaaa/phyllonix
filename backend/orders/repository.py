


from datetime import timedelta
from typing import Any, Dict, List

from fastapi import HTTPException,status
from sqlalchemy import func, select, text, update

from backend.common.utils import now
from backend.orders.constants import RESERVATION_TTL_MINUTES, UPI_RESERVATION_TTL_MINUTES
from backend.schema.full_schema import Cart, CartItem, CheckoutSession, CheckoutStatus, InventoryReservation, InventoryReserveStatus, Product


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
        InventoryReservation.status == InventoryReserveStatus.ACTIVE.value,
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
        status=CheckoutStatus.PROGRESS.value,
        cart_snapshot={"cart_id": cart_id, "items": items},
        expires_at=now() + timedelta(minutes=RESERVATION_TTL_MINUTES),
        selected_payment_method=None
    )
    session.add(cs)
    await session.flush()  # get cs.id

    cs_id = cs.id
    cs_public_id = cs.public_id

    # await reserve_inventory(session,items,cs_id,reserved_until)

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
    stmt = select(CheckoutSession.public_id).where(
        CheckoutSession.user_id == user_id,
        CheckoutSession.expires_at > now(),
        CheckoutSession.status==CheckoutStatus.PROGRESS.value
    )
    res = await session.execute(stmt)
    cs = res.scalar_one_or_none()
    if cs:  
        return {
            "checkout_id": cs.public_id
        }
    
async def get_checkout_details(session,checkout_id,user_id):
    stmt = select(CheckoutSession.id,CheckoutSession.cart_snapshot,CheckoutSession.expires_at
                  ).where(CheckoutSession.public_id == checkout_id,CheckoutSession.user_id==user_id,CheckoutSession.status==CheckoutStatus.PROGRESS.value
                          ).with_for_update()
    res = await session.execute(stmt)
    cs = res.scalar_one_or_none()
    if not cs:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="checkout session not found")

    if cs.expires_at and cs.expires_at < now():
        raise HTTPException(status_code=410, detail="checkout session expired")

    items = cs.cart_snapshot.get("items", []) if cs.cart_snapshot else []
    if not items:
        raise HTTPException(status_code=400, detail="no items in checkout session")
    
    return cs 


async def compute_order_totals(session,items,payment_method,cs_id,checkout_public_id,cs_expires_at):
    # Compute totals
    subtotal = sum(int(it["base_price"]) * int(it["quantity"]) for it in items)
    tax = int(subtotal * 0.02)
    shipping = 50
    discount = 0

    cod_fee = 0
    if payment_method == "COD":
        cod_fee = 50
    total = subtotal + tax + shipping + cod_fee - discount

    # Optionally extend TTL for slower payment methods like UPI
    if payment_method == "UPI":
        cs_expires_at = now() + timedelta(minutes=UPI_RESERVATION_TTL_MINUTES)

    stmt=update(CheckoutSession.selected_payment_method).where(CheckoutSession.id==cs_id).values(selected_payment_method=payment_method)
    await session.execute(stmt)
    await session.commit()

    return {
        "checkout_id": checkout_public_id,
        "selected_payment_method": payment_method,
        "summary": {
            "items": items,
            "subtotal": subtotal,
            "tax": tax,
            "shipping": shipping,
            "cod_fee": cod_fee,
            "discount": discount,
            "total": total,
        },
        "confirm_instructions": {
            "endpoint": f"/checkout/{checkout_public_id}/confirm",
            "method": "POST",
            "idempotency_required": True,
        },
    }
