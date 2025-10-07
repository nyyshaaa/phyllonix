


from datetime import timedelta
from typing import Any, Dict, List

from fastapi import HTTPException,status
from sqlalchemy import case, func, select, text, update

from backend.common.utils import now
from backend.orders.constants import RESERVATION_TTL_MINUTES, UPI_RESERVATION_TTL_MINUTES
from backend.schema.full_schema import Cart, CartItem, CheckoutSession, CheckoutStatus, IdempotencyKey, InventoryReservation, InventoryReserveStatus, Order, OrderItem, OrderStatus, Product


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


async def items_avblty(session, product_ids,product_qts,requested_qts) -> int:
    """Return available = stock_qty - sum(active reservations)."""
    item_errs=[]
    cond = (InventoryReservation.status == InventoryReserveStatus.ACTIVE.value) & (InventoryReservation.reserved_until > now())
    reserved_expr = func.coalesce(func.sum(case([(cond, InventoryReservation.quantity)], else_=0)), 0).label("reserved_qty")
   
    # sum of active reservations
    stmt2 = select(Product.id,reserved_expr).where(Product.id.in_(product_ids)).group_by(Product.id)

    res = await session.execute(stmt2)
    rows = res.all()

    for pid,reserved_qty,product_qty,req_qty in zip(rows,product_qts,requested_qts):
        avbl=max(0,product_qty-reserved_qty)
        if req_qty > avbl:
            item_errs.append({
                "detail": f"Not enough stock for product {pid}: requested={req_qty}, available={avbl}"
            })

    if item_errs:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"errors": item_errs})

    


# create checkout session and resrver inventory atomically 
async def create_checkout_session(session,user_id,cart_id,items,reserved_until):
   
    cs = CheckoutSession(
        user_id=user_id,
        status=CheckoutStatus.PROGRESS.value,
        cart_snapshot={"cart_id": cart_id, "items": items},
        expires_at=reserved_until,
        selected_payment_method=None
    )
    session.add(cs)
    await session.flush()  # get cs.id

    cs_id = cs.id
    cs_public_id = cs.public_id

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

async def spc_by_ikey(session,i_key):
    stmt = select(IdempotencyKey.response_body,IdempotencyKey.response_code
                  ).where(IdempotencyKey.key == i_key).limit(1)  #* check limit 1 
    res = await session.execute(stmt)
    order_npay_data = res.one_or_none()
    if order_npay_data:
        if order_npay_data[0] and order_npay_data[1]:
            return order_npay_data[0]


#* recheck checkout retrieval and correct attr retreive format as per reqd fields
async def validate_checkout(session,checkout_id):
    stmt = select(CheckoutSession.id,CheckoutSession.expires_at,CheckoutSession.selected_payment_method,CheckoutSession.cart_snapshot
                  ).where(CheckoutSession.public_id == checkout_id).with_for_update()
    res = await session.execute(stmt)
    cs = res.scalar_one_or_none()
    cs_id=cs.id
    if not cs:
        raise HTTPException(status_code=404, detail="Checkout session not found")

    # expiration check
    if cs.expires_at and cs.expires_at < now():
        raise HTTPException(status_code=410, detail="Checkout session expired")

    # ensure a payment method has been selected
    if not cs.selected_payment_method:
        raise HTTPException(status_code=400, detail="Payment method not selected")

    payment_method = cs.selected_payment_method  # "UPI" or "COD"

    # Load items from checkout snapshot
    items = cs.cart_snapshot.get("items", []) if cs.cart_snapshot else []
    if not items:
        raise HTTPException(status_code=400, detail="Checkout has no items")


    await validate_reservations_and_total(session,cs_id,items,payment_method)
    

async def validate_reservations_and_total(session,cs_id,items,payment_method):
    stmt = select(InventoryReservation).where(InventoryReservation.checkout_session_id == cs_id)
    res = await session.execute(stmt)
    reservations = res.scalars().all()
    if not reservations:
        raise HTTPException(status_code=409, detail="No reservations found for checkout")

    # Build map product_id -> requested_qty
    requested_by_product = {it["product_id"]: int(it["quantity"]) for it in items}

    # Check each reservation is ACTIVE and not expired and matches requested qty
    for r in reservations:
       
        if r.reserved_until and r.reserved_until < now():
            raise HTTPException(status_code=409, detail=f"Reservation expired for product {r.product_id}")

        req_qty = requested_by_product.get(r.product_id, 0)
        if req_qty == 0 or r.quantity != req_qty:
            # mismatch: client snapshot or reservation mismatch
            raise HTTPException(status_code=409, detail=f"Reservation mismatch for product {r.product_id}")
        
        order_total=compute_final_total(items,payment_method)

        return order_total
        

def compute_final_total(items,payment_method):
    subtotal = 0
    for it in items:
        subtotal += int(it["base_price"]) * int(it["quantity"])
    tax = int(subtotal * 0.02)
    shipping = 0
    discount = 0
    cod_fee = 50 if payment_method == "COD" else 0
    total = subtotal + tax + shipping + cod_fee - discount
    return total


async def create_order_with_items(session,user_id,payment_method,subtotal,tax,shipping,discount,total,items):
    # Create Order
    order = Order(
        user_id=user_id,
        # session_id=session_id,
        status=OrderStatus.PENDING_PAYMENT.value if payment_method == "UPI" else OrderStatus.CONFIRMED.value,
        subtotal=subtotal,
        tax=tax,
        shipping=shipping,
        discount=discount,
        total=total,
        placed_at=None if payment_method == "UPI" else now(),
        created_at=now(),
        updated_at=now(),
    )
    session.add(order)
    await session.flush()  # to get order.id

    # Create OrderItem rows
    for it in items:
        oi = OrderItem(
            order_id=order.id,
            product_id=it["product_id"],
            sku=None,
            quantity=it["quantity"],
            unit_price_snapshot=it["base_price"],
            tax_snapshot=int((it["base_price"] * it["quantity"]) * 0.02),
            discount_snapshot=0,
        )
        session.add(oi)