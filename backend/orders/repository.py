


from datetime import timedelta
from typing import Any, Dict, List

from fastapi import HTTPException,status
from sqlalchemy import case, func, select, text, update

from backend.common.utils import now
from backend.orders.constants import RESERVATION_TTL_MINUTES, UPI_RESERVATION_TTL_MINUTES
from backend.schema.full_schema import Cart, CartItem, CheckoutSession, CheckoutStatus, IdempotencyKey, InventoryReservation, InventoryReserveStatus, Order, OrderItem, OrderStatus, Payment, PaymentAttempt, Product


async def capture_cart_snapshot(session, user_id: int) -> List[Dict[str, Any]]:
    
    stmt = (
        select(Cart.id.label("cart_id"),CartItem.id.label("cart_item_id"), 
               CartItem.product_id, CartItem.quantity, Product.base_price , Product.stock_qty)
        .join(Cart,Cart.id==CartItem.cart_id)
        .join(Product, Product.id == CartItem.product_id)
        .where(Cart.user_id == user_id)
    )
    res = await session.execute(stmt)
    rows = res.all()
    first = rows[0]
    cart_id = int(first.cart_id)
    if cart_id is None :
        raise HTTPException()
        
    items = []
    for r in rows:
        items.append({
            "cart_item_id": int(r.cart_item_id),
            "product_id": int(r.product_id),
            "quantity": int(r.quantity),
            "prod_base_price": int(r.base_price),
            "product_stock": int(r.stock_qty),
        })
    return {
        "cart_id":cart_id,
        "items":items
    }


async def items_avblty(session,product_ids,product_data) -> int:
    """Return available = stock_qty - sum(active reservations)."""
    item_errs=[]
    cond = (InventoryReservation.status == InventoryReserveStatus.ACTIVE.value) & (InventoryReservation.reserved_until > now())
    reserved_expr = func.coalesce(func.sum(case([(cond, InventoryReservation.quantity)], else_=0)), 0).label("reserved_qty")
   
    # sum of active reservations
    stmt = (
        select(InventoryReservation.product_id, reserved_expr)
        .where(InventoryReservation.product_id.in_(product_ids))
        .group_by(InventoryReservation.product_id)
    )
    res = await session.execute(stmt)
    rows = res.all()
    reserved_map = {row[0]: int(row[1]) for row in rows} 

    for pid,prod_dict in product_data.items():
        stock_qty = prod_dict["stock_qty"]
        requested_qty = prod_dict["requested_qty"]
        reserved_qty = reserved_map.get(pid, 0)
        avbl=max(0,stock_qty-reserved_qty)
        if requested_qty > avbl:
            item_errs.append({
                "detail": f"Not enough stock for product {pid}: requested={requested_qty}, available={avbl}"
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
        CheckoutSession.status == CheckoutStatus.PROGRESS.value,
        CheckoutSession.expires_at > now()
    )
    res = await session.execute(stmt)
    cs = res.scalar_one_or_none()
    if cs:  
        return {
            "checkout_id": cs.public_id
        }
    return None
    
async def get_checkout_details(session,checkout_id,user_id):
    stmt = select(CheckoutSession.id,CheckoutSession.cart_snapshot,CheckoutSession.expires_at
                  ).where(CheckoutSession.public_id == checkout_id,CheckoutSession.user_id==user_id,CheckoutSession.status==CheckoutStatus.PROGRESS.value
                          ).with_for_update()
    res = await session.execute(stmt)
    cs = res.one_or_none()
    cs_dict = {"cs_id":cs[0],"cs_cart_snap":cs[1],"cs_expires_at":cs[2]}
   
    if not cs:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="checkout session not found")

    if cs_dict["cs_expires_at"] and cs_dict["cs_expires_at"] < now():
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="checkout session expired")

    items = cs_dict["cs_cart_snap"].get("items", [])
    if not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no items in checkout session")
    
    return cs_dict 


async def order_totals_n_checkout_updates(session,items,payment_method,cs_id,checkout_public_id,cs_expires_at):
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
    
    #** if want to return with response
    # "confirm_instructions": {
        #     "endpoint": f"/checkout/{checkout_public_id}/confirm",
        #     "method": "POST",
        #     "idempotency_required": True,
    # },

    return {
        "checkout_id": checkout_public_id,
        "selected_payment_method": payment_method,
        "items": items,
        "summary": {
            "subtotal": subtotal,
            "tax": tax,
            "shipping": shipping,
            "cod_fee": cod_fee,
            "discount": discount,
            "total": total,
        },
    }

async def spc_by_ikey(session,i_key):
    stmt = select(IdempotencyKey.response_body,IdempotencyKey.response_code
                  ).where(IdempotencyKey.key == i_key).limit(1)  #* check limit 1 
    res = await session.execute(stmt)
    res = res.one_or_none()
    if res:
        order_npay_data = {"response_body":res[0],"response_code":res[1]}
        return order_npay_data[0]
    return res


#* recheck checkout retrieval and correct attr retreive format as per reqd fields
async def validate_checkout_nget_totals(session,checkout_id):
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

    #** keep the same expiry for checkout and invenotry hold and avoid the work of revalidating inventory hence optimising latency .      
    # await validate_reservations(session,cs_id,items,payment_method)


    order_totals=compute_final_total(items,payment_method)
    return order_totals,payment_method

    

async def validate_reservations(session,cs_id,items,payment_method):
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
        
        

def compute_final_total(items,payment_method):
    subtotal = 0
    for it in items:
        subtotal += int(it["base_price"]) * int(it["quantity"])
    tax = int(subtotal * 0.02)
    shipping = 0
    discount = 0
    cod_fee = 50 if payment_method == "COD" else 0
    total = subtotal + tax + shipping + cod_fee - discount

    return {
        "items" : items,
        "subtotal": subtotal,
        "tax": tax,
        "shipping": shipping,
        "cod_fee": cod_fee,
        "discount": discount,
        "total": total,
    }


async def place_order_with_items(session,user_id,payment_method,order_totals,i_key):

    # Create Order
    order = Order(
        user_id=user_id,
        # session_id=session_id,
        status=OrderStatus.PENDING_PAYMENT.value if payment_method == "UPI" else OrderStatus.CONFIRMED.value,
        subtotal=order_totals["subtotal"],
        tax=order_totals["tax"],
        shipping=order_totals["shipping"],
        discount=order_totals["discount"],
        total=order_totals["total"],
        placed_at=None if payment_method == "UPI" else now(),
        created_at=now(),
        updated_at=now(),
    )
    session.add(order)
    await session.flush()  # to get order.id

    # Create OrderItem rows
    for it in order_totals["items"]:
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

    #** update product stock and stuff via bg workers , emit order place event .

    response = {
        "order_public_id": order.public_id,
        "order_id": order.id,
        "status": order.status
    }
    

    if payment_method == "UPI" :
        pay_public_id=await record_payment_attempt(session,order.id,order_totals["total"])
        await commit_idempotent_order_place(session,i_key,order.id,
                                            None,response_body=None,owner_type="order_confirm")
        
        response["pay_public_id"]=pay_public_id
        return response

    await commit_idempotent_order_place(session,i_key,order.id,
                                        200,response_body=response,owner_type="order_confirm")

    return response

#** check this owner type thing and see if need to save event 
async def commit_idempotent_order_place(session,idempotency_key,owner_id,response_code,response_body,owner_type):
    ik = IdempotencyKey(
            key=idempotency_key,
            owner_type=owner_type,
            owner_id=owner_id,
            response_code=response_code,
            response_body=response_body,
            expires_at=now + timedelta(days=1),
        )
    session.add(ik)
    
    # commit here after saving idempotency of operation
    await session.commit()

    


async def record_payment_attempt(session,order_id,order_total):
  
    payment = Payment(
        order_id=order_id,
        # provider="razorpay", 
        provider_payment_id=None,
        status="PENDING",
        amount=order_total
    )
    session.add(payment)
    await session.flush()

    # record a payment attempt
    pa = PaymentAttempt(
        payment_id=payment.id,
        attempt_no=1,
        provider_response=None,
        provider_event_id=None,
    )
    session.add(pa)
    await session.flush()

    return payment.public_id

#** update staus as well
async def update_payment_status(session,pay_public_id,provider_order_id):
    stmt = update(Payment).where(Payment.public_id==pay_public_id).values(provider_payment_id=provider_order_id).returning(Payment.id)
    res=await session.execute(stmt)
    res=res.first[0] if res else None

#** also update provider event id and also check if to convert resp to any format 
async def update_payment_attempt(session,pay_id,psp_resp):
    stmt = update(PaymentAttempt).where(PaymentAttempt.payment_id==pay_id).values(provider_response=psp_resp)
    await session.execute(stmt)


async def update_idempotent_response(session, key: str, code: int, body: dict):
    stmt = update(IdempotencyKey).where(IdempotencyKey.key==key
                                        ).values(response_code=code,response_body=body)
    await session.execute(stmt)

