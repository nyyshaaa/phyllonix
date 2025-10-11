


from datetime import timedelta
from typing import Any, Dict, List

from fastapi import HTTPException,status
from sqlalchemy import Tuple, and_, case, func, select, text, update

from backend.common.utils import now
from backend.orders.constants import RESERVATION_TTL_MINUTES, UPI_RESERVATION_TTL_MINUTES
from backend.schema.full_schema import Cart, CartItem, CheckoutSession, CheckoutStatus, IdempotencyKey, InventoryReservation, InventoryReserveStatus, Order, OrderItem, OrderStatus, Payment, PaymentAttempt, PaymentStatus, Product


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
                  ).where(IdempotencyKey.key == i_key)
    res = await session.execute(stmt)
    res = res.one_or_none()
    if res:
        order_npay_data = {"response_body":res[0],"response_code":res[1]}
        return order_npay_data
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
    if cs.expires_at and cs.expires_at < now()+timedelta(seconds=40):
        raise HTTPException(status_code=410, detail="Checkout session expired")

    # ensure a payment method has been selected
    if not cs.selected_payment_method:
        raise HTTPException(status_code=400, detail="Payment method not selected")

    payment_method = cs.selected_payment_method  # "UPI" or "COD"

    # Load items from checkout snapshot
    items = cs.cart_snapshot.get("items", []) if cs.cart_snapshot else []
    if not items:
        raise HTTPException(status_code=400, detail="Checkout has no items")

    #** avoid the work of revalidating inventory hence optimising latency checked in earlier endpoint path . inventory hold expiry is longer than checkout expiry .    
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
        pay_public_id=await record_payment_init_pending(session,order.id,order_totals["total"])
        await commit_idempotent_order_place(session,i_key,order.id,
                                            None,response_body=None,owner_type="payment_pending")
        
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

    

async def record_payment_init_pending(session,order_id,order_total):
  
    payment = Payment(
        order_id=order_id,
        # provider="razorpay", 
        provider_payment_id=None,
        status=PaymentStatus.PENDING.value,
        amount=order_total
    )
    session.add(payment)
    await session.flush()

    # # record a payment attempt
    # pa = PaymentAttempt(
    #     payment_id=payment.id,
    #     attempt_no=1,
    #     provider_response=None,
    #     provider_event_id=None,
    # )
    # session.add(pa)
    # await session.flush()

    return payment.public_id

#** update staus as well
async def update_payment_provider_id(session,pay_public_id,provider_order_id):
    stmt = update(Payment).where(Payment.public_id==pay_public_id).values(provider_payment_id=provider_order_id).returning(Payment.id)
    res=await session.execute(stmt)
    res=res.first[0] if res else None

#** also update provider event id and also check if to convert resp to any format 
async def update_payment_attempt_psp_resp(session,pay_id,psp_resp):
    stmt = update(PaymentAttempt).where(PaymentAttempt.payment_id==pay_id).values(provider_response=psp_resp)
    await session.execute(stmt)

async def update_payment_attempt_resp(session,attempt_id,status,psp_response):
    stmt= update(PaymentAttempt
                 ).where(PaymentAttempt.id == attempt_id
                ).values(
                    status=status,
                    provider_response=psp_response,
                    updated_at=now()
                )
    await session.execute(stmt)

# async def get_pay_attempt_id(session,payment_id):
#     stmt = select(PaymentAttempt.id
#                   ).where(PaymentAttempt.payment_id == payment_id,PaymentAttempt.attempt_no == 1)
#     res = await session.execute(stmt)
#     attempt_row = res.scalar_one_or_none()
#     attempt_id = attempt_row.id if attempt_row else None

async def record_payment_attempt(session,payment_id,attempt_no,pay_status,resp):
    pa = PaymentAttempt(
        payment_id=payment_id,
        attempt_no=attempt_no,
        status=pay_status,
        provider_response=None,
        created_at=now(),
    )
    session.add(pa)
    # flush to get id
    await session.flush()
    attempt_id = pa.id
    return attempt_id



async def update_idempotent_response(session, key: str, code: int, body: dict):
    stmt = update(IdempotencyKey).where(IdempotencyKey.key==key
                                        ).values(response_code=code,response_body=body)
    await session.execute(stmt)


async def get_payment_order_id(session,provider_payment_id):
    stmt = select(Payment.order_id).where(Payment.provider_payment_id == provider_payment_id)
    res = await session.execute(stmt)
    payment_order_id = res.scalar_one_or_none()
    return payment_order_id

async def update_pay_success_get_orderid(session,provider_payment_id,payment_status):
    stmt = (
    update(Payment.order_id)
    .where(Payment.provider_payment_id == provider_payment_id) 
    .values(
        status=payment_status,
        paid_at=now(),
        updated_at=now()
    ).returning(Payment.order_id))
    result=await session.execute(stmt)
    order_id = result.scalar_one_or_none()
    return order_id

async def update_order_status_get_orderid(session,payment_order_id,order_status):
  
    stmt = (
        update(Order)
        .where(Order.id == payment_order_id)
        .values(
            status=order_status,
            placed_at=func.now(),
            updated_at=func.now()
        )
        .returning(Order.id)
    )
    result = await session.execute(stmt)
    order_id = result.scalar_one_or_none()
    return order_id


async def commit_reservations_and_decrement_stock(session,order_id):
    """
    Idempotent commit: for each reservation linked to the order:
      - ensure reservation.status != COMMITTED
      - decrement product.stock_qty atomically (UPDATE ... WHERE stock_qty >= q)
      - set reservation.status = COMMITTED
    """
    # fetch minimal reservation data and lock rows
    stmt = (
        select(
            InventoryReservation.id,
            InventoryReservation.product_id,
            InventoryReservation.quantity,
        )
        .where(
            InventoryReservation.order_id == order_id,
            InventoryReservation.status.in_(InventoryReserveStatus.ACTIVE.value),
        )
        .with_for_update()  # lock reservations so other txs don't concurrently commit them
    )

    res = await session.execute(stmt)
    rows: List[Tuple] = res.all()
    if not rows:
        return []  # nothing to commit
    
    committed_res_ids: List[int] = []
    committed_at = now()

    for res_row in rows:
        iv_id, product_id, qty = res_row
        q = int(qty)
        pid = int(product_id)

        prod_update_errs = []

        prod_update = (
                update(Product)
                .where(and_(Product.id == pid, Product.stock_qty >= q))
                .values(stock_qty=Product.stock_qty - q)
        )
        prod_result = await session.execute(prod_update)
        # prod_result.rowcount should be 1 if update succeeded (stock >= q), otherwise 0
        if prod_result.rowcount == 0:
            # Either product not found OR stock insufficient OR concurrent change
            #** log it , also check how to handle it properly webhook shouldn't retry in case of concurrent update or if product stock rem is low--
            #-- product not found shouldn't happen--
            #-- for now just append and don't do anything with it 
            prod_update_errs.append(
                {"detail":f"Insufficient stock or concurrent modification for product {pid} while committing reservation {iv_id}"})
        
        iv_update = (
            update(InventoryReservation)
            .where(
                and_(
                    InventoryReservation.id == iv_id,
                    InventoryReservation.status.in_(InventoryReserveStatus.ACTIVE.value),
                )
            )
            .values(status=InventoryReserveStatus.COMMITED.value, committed_at=committed_at)
        )
        iv_result = await session.execute(iv_update)
        # If iv_result.rowcount == 0, someone else may have committed it already — that's fine (idempotency).
        if iv_result.rowcount >= 1:
            committed_res_ids.append(iv_id)
        else:
            # someone else committed it concurrently; we didn't modify it, but the product decrement happened
            # We'll treat it as idempotent and continue; but log/raise if needed.
            # OPTIONAL: log warning here about concurrent commit.
            pass

    await session.flush()
    return committed_res_ids
