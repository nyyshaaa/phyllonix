
import asyncio
import json
from uuid6 import uuid7
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from fastapi import HTTPException,status
from sqlalchemy import Tuple, and_, case, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from backend.common.utils import build_success, json_ok, now
from backend.orders.constants import RESERVATION_TTL_MINUTES, UPI_RESERVATION_TTL_MINUTES
from backend.schema.full_schema import Cart, CartItem, CheckoutSession, CheckoutStatus, CommitIntent, CommitIntentStatus, IdempotencyKey, InventoryReservation, InventoryReserveStatus, Orders, OrderItem, OrderStatus, OutboxEvent, OutboxEventStatus, Payment, PaymentAttempt, PaymentStatus, Product


async def capture_cart_snapshot(session, user_id: int) -> List[Dict[str, Any]]:
    
    stmt = (
        select(Cart.id.label("cart_id"),CartItem.id.label("cart_item_id"), 
               Product.id.label("product_id"), CartItem.quantity, Product.base_price , Product.stock_qty)
        .join(Cart,Cart.id==CartItem.cart_id)
        .join(Product, Product.id == CartItem.product_id)
        .where(Cart.user_id == user_id)
        .with_for_update(of=Product, nowait=False) 
    )
    res = await session.execute(stmt)
    rows = res.all()
    first = rows[0]
    cart_id = int(first.cart_id)
    if cart_id is None :
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart not found for user")
        
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
    reserved_expr = func.coalesce(func.sum(case((cond, InventoryReservation.quantity), else_=0)), 0).label("reserved_qty")
   
    # sum of active reservations for products in checkout 
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
    
    #* depending on business requirements just return raise 
    if item_errs:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"errors": item_errs})

    


async def get_or_create_checkout_session(session,user_id,reserved_until):
    """Create a new checkout session for the user and if active valid checkout exists return that .
    On conflcit integrity don't raise get valid checkout if avbl .
    Catch other integrity issues and rollback .
    """

    values = {
        "public_id": uuid7(),
        "user_id": user_id,
        "expires_at": reserved_until,
        "selected_payment_method": None,
        "is_active": True,
        "created_at": now(),
        "updated_at": now(),
    }

    insert_stmt = (
        pg_insert(CheckoutSession)
        .values(**values)
        .on_conflict_do_nothing(
            index_elements=["user_id"],
            index_where=text("is_active = true"),
        )
        .returning(CheckoutSession.public_id)
    )

    try:
        result = await session.execute(insert_stmt)
        checkout_pid = result.scalar_one_or_none()
        
        if checkout_pid:
            await session.commit()
            return checkout_pid
        
        # conflict happened , return existing checkout is active 
        checkout_pid = await get_checkout_session(session,user_id)
        print(checkout_pid)

        if checkout_pid:
            return checkout_pid
        
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not create checkout session please retry",   # if other txn marked checkout inactive after processing and we returned no chekout_pid via get 
        )
    except IntegrityError as e:
        print(e)
        await session.rollback()
        #* log the error for debug and audit 
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=f"Integrity Error other than unique violation occured in db")
    

async def reserve_inventory(session,cart_items,cs_id,reserved_until):

    to_insert = []

    for it in cart_items:
        print("cs_id",cs_id)
        row = {
            "product_id": int(it["product_id"]),
            "checkout_id": cs_id,  
            "quantity": int(it["quantity"]),
            "reserved_until": reserved_until,
            "status": InventoryReserveStatus.ACTIVE.value,
            "created_at": now(),
        }
        to_insert.append(row)

    insert_stmt = pg_insert(InventoryReservation).values(to_insert)
    insert_stmt = insert_stmt.on_conflict_do_nothing(index_elements=["checkout_id", "product_id"])

    try:
        await session.execute(insert_stmt)
        
    except IntegrityError as bulk_exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail=f"{bulk_exc} exception occured while reserving inventory")


async def get_checkout_session(session,user_id):
  
    # Reuse active checkout session if exists
    stmt = select(CheckoutSession.id,CheckoutSession.public_id,CheckoutSession.expires_at).where(
        CheckoutSession.user_id == user_id,
        CheckoutSession.is_active.is_(True),
    )
    res = await session.execute(stmt)
    cs = res.one_or_none()

    if not cs:
        return None
    
    if cs[2] < now():  
        await update_checkout_activeness(session,cs[0])
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="checkout session expired")
    return cs[1]
    
async def get_checkout_details(session,checkout_id,user_id):
    stmt = select(CheckoutSession.id,CheckoutSession.expires_at,CheckoutSession.cart_snapshot,CheckoutSession.selected_payment_method
                  ).where(CheckoutSession.user_id==user_id,CheckoutSession.is_active.is_(True),
                          CheckoutSession.public_id==checkout_id
                          )
    res = await session.execute(stmt)
    cs = res.one_or_none()
    cs_dict = {"cs_id":cs[0],"cs_expires_at":cs[1],"cs_cart_snap":cs[2],"cs_pay_method":cs[3]}
   
    if not cs:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="checkout session not found")

    if cs_dict["cs_expires_at"] < now():
        await update_checkout_activeness(session,cs[0],is_active=False)
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="checkout session expired")
    
    return cs_dict 



async def update_checkout_activeness(session,cs_id,is_active:bool = False):
    stmt = update(CheckoutSession
                  ).where(CheckoutSession.id == cs_id).values(is_active=False)
    
    await session.execute(stmt)
    await session.commit()


async def update_checkout_cart_n_paymethod(session,cs_id,payment_method,items):
    print("in update checkout part ", cs_id)
    stmt=update(CheckoutSession).where(CheckoutSession.id==cs_id
                                       ).values(selected_payment_method=payment_method,
                                                cart_snapshot=items)
    await session.execute(stmt)

async def spc_by_ikey(session,i_key,user_id):
    stmt = select(IdempotencyKey.response_body,IdempotencyKey.response_code,IdempotencyKey.expires_at
                  ).where(IdempotencyKey.key == i_key,IdempotencyKey.created_by == user_id)
    res = await session.execute(stmt)
    res = res.one_or_none()
    if res and res[2] < now( ) + timedelta(seconds=40):
        raise HTTPException(status_code=status.HTTP_410_GONE,detail="Checkout already expired")
    if res:
        order_npay_data = {"response_body":res[0],"response_code":res[1]}
        return order_npay_data
    return res


async def response_by_ikey(session,idempotency_key,user_identifier):
    order_npay_data = await spc_by_ikey(session,idempotency_key,user_identifier)
    if order_npay_data and order_npay_data["response_body"] is not None:
        payload = build_success(order_npay_data, trace_id=None)
        return json_ok(payload)

async def validate_checkout_get_items_paymethod(session,checkout_id,user_id):
    stmt = select(CheckoutSession.id,CheckoutSession.expires_at,CheckoutSession.selected_payment_method,CheckoutSession.cart_snapshot
                  ).where(CheckoutSession.user_id==user_id,CheckoutSession.is_active.is_(True),
                      CheckoutSession.public_id == checkout_id).with_for_update()
    res = await session.execute(stmt)
    cs = res.one_or_none()
    cs_id=cs[0]
    if not cs:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Checkout session not found or unauthorized")
    
    #** check concurrency here it may lead one request to fail and one to succeed , 
    # by default concurrent requests must not be allowed for this endpoint from frontend side
    if cs[1] and cs[1] < now()+timedelta(seconds=40):
        await update_checkout_activeness(session,cs[0])
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Checkout session expired")

    # ensure a payment method has been selected
    if not cs[2]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment method not selected")

    payment_method = cs[2]  # "UPI" or "COD"

    # Load items from checkout snapshot
    items = cs[3].get("items", []) if cs[3] else []
    if not items:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Checkout has no items")
    
    return cs_id,items,payment_method


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
        subtotal += int(it["prod_base_price"]) * int(it["quantity"])
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

#** modify it to be concurrent safe
#** 1 idemotency key in table at first 
#** 2 if creation of idempotency record happens flush and proceed to create order , orderitems and record payment initiation(paymnet pending) in same single commit 
#** 3 update the idempotency table with response body and code under same single commit .
#** 4 if integrity conflict occured in first idempotency creation check if response code and body exists 
#** with ikey if yes retrurn otheriwse raise conflict issue to client so that user may safely retry .
async def place_order_with_items(session,user_id,payment_method,order_totals,i_key):

    # Create Order
    order = Orders(
        user_id=user_id,
        # session_id=session_id,
        status=OrderStatus.PENDING_PAYMENT.value if payment_method == "UPI" else OrderStatus.CONFIRMED.value,
        subtotal=order_totals["subtotal"],
        tax=order_totals["tax"],
        shipping=order_totals["shipping"],
        discount=order_totals["discount"],
        total=order_totals["total"],
        placed_at= now(),
        created_at=now(),
        updated_at=now(),
        shipping_address_json={"city":"central city","country":"america"}  #** just a placeholder of address for testing,insert actual addresses here 
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
            unit_price_snapshot=it["prod_base_price"],
            tax_snapshot=int((it["prod_base_price"] * it["quantity"]) * 0.02),
            discount_snapshot=0,
        )
        session.add(oi)

    response = {
        "order_public_id": order.public_id,
        "order_id": order.id,
        "status": order.status
    }
    

    if payment_method == "UPI" :
        pay_public_id=await record_payment_init_pending(session,order.id,order_totals["total"])
        await update_order_idempotency_record(session,user_id,i_key,order.id,
                                            None,response_body=None,owner_type="pay_now")
        
        response["pay_public_id"]=pay_public_id
        return response

    await update_order_idempotency_record(session,user_id,i_key,order.id,
                                        200,response_body=response,owner_type="order_confirm")
    
    #** if order was cod then record intent of order.received_for_fulfillment in db, 
    # an extrenal worker will poll pending events and publish them to extrenal queue , mark it sent in db and then extrenal workers will process them .
    # for project just publish them to in memory queue here and then workers will pick tasks from queue and execute them .
    #** as this is a test project so here just simulate the event of   order.received_for_fulfillment as there won't be any actual fulfillment of order .

    return response


async def bulk_insert_order_items(session,order,order_totals):
    item_rows = []
    for it in order_totals["items"]:
        item_rows.append({
            "order_id": order.id,
            "product_id": int(it["product_id"]),
            "quantity": int(it["quantity"]),
            "unit_price_snapshot": int(it["prod_base_price"]),
            "tax_snapshot": int(it.get("tax_snapshot", int((it["prod_base_price"] * it["quantity"]) * 0.02))),
            "discount_snapshot": int(it.get("discount_snapshot", 0)),
            "created_at": now(),
            "updated_at": now(),
        })

    if item_rows:
        insert_stmt = pg_insert(OrderItem).values(item_rows)
        insert_stmt = insert_stmt.on_conflict_do_nothing()
        await session.execute(insert_stmt)


async def update_order_idempotency_record(session, user_id, ik_id, owner_id,
                                        response_code, response_body, owner_type):
    if response_body:
        response_body = json.dumps(response_body)
        
    stmt = (
        update(IdempotencyKey)
        .where(
            and_(
                IdempotencyKey.id == ik_id,
                IdempotencyKey.created_by == user_id
            )
        )
        .values(
            owner_id=owner_id,
            owner_type=owner_type,
            response_body=response_body,
            response_code=response_code
        )
    )
    
    await session.execute(stmt)
    await session.flush()


async def record_order_idempotency(session, idempotency_key, user_identifier):
  
    now_ts = now()
    insert_values = {
        "key": idempotency_key,
        "owner_id": None,
        "response_code": None,
        "response_body": None,
        "created_by": user_identifier,
        "created_at": now_ts,
        "expires_at": now_ts + timedelta(days=1)
    }

    insert_stmt = pg_insert(IdempotencyKey).values(insert_values).on_conflict_do_nothing().returning(IdempotencyKey.id)
    res = await session.execute(insert_stmt)
    ik_id = res.scalar_one_or_none()


    if not ik_id :

        await asyncio.sleep(5)

        order_npay_data = await spc_by_ikey(session,idempotency_key,user_identifier)
        if order_npay_data and order_npay_data["response_body"] is not None:
            payload = build_success(order_npay_data, trace_id=None)
            return json_ok(payload)
        # to be completely secure in case if lock got failed for all requests midprocess so here if not ik_id(implying it already inserted) so wait for few seconds 
        # and then get response data by ikey if fouund return otherwise return 202 accepted to short circuit it here so that concurrent doesn't proceed .
    
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


#** check if need to save event and also properly fix on conflict to do nothing or get data
# idempotent in concurrency via i key 
async def commit_idempotent_order_place(session,user_id,idempotency_key,owner_id,response_code,response_body,owner_type):# idempotent 
    stmt = select(IdempotencyKey.id).where(IdempotencyKey.key==idempotency_key)
    res = await session.execute(stmt)

    res = res.scalar_one_or_none()
    
    if res :
        return 

        
    ik = IdempotencyKey(
            key=idempotency_key,
            owner_type=owner_type,
            owner_id=owner_id,
            response_code=response_code,
            response_body=response_body,
            expires_at=now() + timedelta(days=1),
            created_by = user_id
        )
    
    try:
        session.add(ik)
    except IntegrityError:
        session.rollback()
        # stmt = select(IdempotencyKey).where(IdempotencyKey.key==idempotency_key)
        # await session.execute(stmt)

#** update staus as well
async def update_payment_provider_orderid(session,pay_id,provider_order_id):
    stmt = update(Payment).where(Payment.id==pay_id).values(provider_order_id=provider_order_id).returning(Payment.id)
    res=await session.execute(stmt)
    res= res.scalar_one_or_none()

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

async def update_pay_completion_get_orderid(session,provider_order_id,provider_payment_id,payment_status):

    stmt = (
    update(Payment)
    .where(Payment.provider_order_id == provider_order_id) 
    .values(
        status=payment_status,
        paid_at=now(),
        provider_payment_id=provider_payment_id
    ).returning(Payment.order_id))
    result=await session.execute(stmt)
    order_id = result.scalar_one_or_none()
    print("order ",order_id)
    return order_id

async def update_order_status(session,payment_order_id,order_status):
  
    stmt = (
        update(Orders)
        .where(Orders.id == payment_order_id)
        .values(
            status=order_status,
            placed_at=func.now(),
            updated_at=func.now()
        )
        .returning(Orders.id)
    )
    await session.execute(stmt)

async def emit_outbox_event(session, topic: str, payload: dict,
                            aggregate_type: Optional[str] = None,
                            aggregate_id: Optional[int] = None,
                            next_retry_at: Optional[datetime] = None):
   
    values = {
        "topic": topic,
        "payload": payload,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "status": OutboxEventStatus.PENDING,
        "attempts": 0,
        "next_retry_at": next_retry_at,
        "created_at": now(),
    }

    
    stmt = pg_insert(OutboxEvent).values(**values).on_conflict_do_nothing(
        constraint = "uq_outboxevent_aggid_type_topic"
    ).returning(OutboxEvent.id)
    res = await session.execute(stmt)
    ev_id = res.scalar_one_or_none()

    if not ev_id:
        stmt2 = select(OutboxEvent.id).where(
        and_(
            OutboxEvent.aggregate_id.is_(aggregate_id),
            OutboxEvent.aggregate_type.is_(aggregate_type),
            OutboxEvent.topic.is_(topic)
        )
    )
        res = await session.execute(stmt2)
        ev_id =  res.scalar_one_or_none()


async def load_order_items_for_commit(session, order_id: int):
    
    stmt = select(OrderItem.product_id, OrderItem.quantity).where(OrderItem.order_id == order_id)
    res = await session.execute(stmt)
    rows = res.all()
    return [{"product_id": int(r[0]), "quantity": int(r[1])} for r in rows]


async def create_commit_intent(session, order_id: int, reason: str, aggr_type : str , payload: dict):
   
    stmt = pg_insert(CommitIntent).values(
        order_id=order_id,
        reason=reason,
        status=CommitIntentStatus.PENDING,
        payload=payload,
        attempts=0,
        created_at=now(),
    ).on_conflict_do_nothing(
        constraint = "uq_commitintent_aggid_type_reason"  # create a unique index on (order_id, reason) in migration
    ).returning(CommitIntent.id)
    res = await session.execute(stmt)
    commit_intent_id = res.scalar_one_or_none()
    if not commit_intent_id:
        # already exists -> return existing
        stmt = select(CommitIntent).where(CommitIntent.aggregate_id.is_(order_id), 
                                          CommitIntent.aggregate_type.is_(aggr_type), CommitIntent.reason.is_(reason))
        res3 = await session.execute(stmt)
        return res3.scalar_one_or_none()
   
    

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
            InventoryReservation.status.is_(InventoryReserveStatus.ACTIVE.value),
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


async def short_circuit_concurrent_req(session,i_key,user_id,checkout_id):
    res = await spc_by_ikey(session,i_key,user_id)
    if res and res["response_body"]:
        payload = build_success(res, trace_id=None)
        return json_ok(payload)
    
    # else, still in-progress -> instruct client to poll (fail-fast)
    status_url = f"/api/v1/checkout/{checkout_id}/status/{i_key}"
    headers = {"Retry-After": "3", "Location": status_url}
    content={"status": "in_progress", "status_url": status_url, "retry_after": 3}

    payload = build_success(content, trace_id=None)
    return json_ok(payload,status_code=202,headers=headers)


async def sim_emit_outbox_event(session,topic,payload,agg_type,agg_id):
    pass