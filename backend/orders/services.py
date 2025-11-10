

import asyncio
import hashlib
import hmac
import json
import uuid
from typing import Optional
from fastapi import HTTPException, Request, Response , status
import httpx
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from backend.common.utils import now
from backend.orders.repository import commit_reservations_and_decrement_stock, items_avblty, record_payment_attempt, update_idempotent_response, update_pay_completion_get_orderid, update_payment_attempt_resp, update_payment_provider_orderid
from backend.config.settings import config_settings
from backend.schema.full_schema import OrderItem, Orders, OrderStatus, Payment, PaymentAttempt, PaymentAttemptStatus, PaymentEventStatus, PaymentStatus, PaymentWebhookEvent
from sqlalchemy.dialects.postgresql import insert as pg_insert

PSP_API_BASE=config_settings.RZPAY_GATEWAY_URL
PSP_KEY_ID=config_settings.RZPAY_KEY
PSP_KEY_SECRET=config_settings.RZPAY_SECRET
RAZORPAY_WEBHOOK_SECRET=config_settings.RAZORPAY_WEBHOOK_SECRET
TRANSIENT_EXCEPTIONS = (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.NetworkError)
DEFAULT_RETRIES=3
DEFAULT_BACKOFF_BASE = 0.5 


async def validate_items_avblty(session,cart_items):
    
    product_ids=[]
    product_data={}
    for it in cart_items:
        product_ids.append(int(it["product_id"]))
        product_data[int(it["product_id"])]={
        "stock_qty": int(it["product_stock"]),
        "requested_qty": int(it["quantity"]),
        }

    await items_avblty(session,product_ids,product_data)

async def create_psp_order(amount_paise: int, currency: str, receipt: str, notes: dict,
                           
                           idempotency_key: Optional[str] = None,timeout: float = 10.0) -> dict:
    """
    Create Razorpay order (server -> razorpay). Returns dict with provider order id and client payload.
    amount_rs: integer rs 
    receipt: your internal receipt id (e.g., "order_pubid")
    notes: optional metadata
    """
    url = f"{PSP_API_BASE}/orders"
    headers = {
        "Content-Type": "application/json",
    }
    if idempotency_key:
        print("ikey",idempotency_key)
        print(type(idempotency_key))
        headers["Idempotency-Key"] = str(idempotency_key)
    payload = {
        "amount": amount_paise,
        "currency": currency,
        "receipt": receipt,
        "notes": notes or {},
    }
    print(payload,type(payload))
    async with httpx.AsyncClient(timeout=10.0, auth=(PSP_KEY_ID, PSP_KEY_SECRET)) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        print("spsp_data",data)
        return data


async def pay_id_by_public_payid(session,pay_public_id):
    stmt= select(Payment.id).where(Payment.public_id==pay_public_id)
    res = await session.execute(stmt)
    res = res.scalar_one_or_none()
    return res


#** check the commits placement here
async def create_payment_intent(session,idempotency_key,order_totals,order_data,create_psp_order=create_psp_order):
    pay_public_id=order_data["pay_public_id"]
   
    # amount expected in paise
    amount_in_paise = order_totals["total"]*100


    currency = "INR"
    # receipt = f"order_{uuid.uuid4().hex[:20]}"
    receipt = f"order_{str(order_data['order_public_id'])[:20]}"
    notes = {"order_public_id": str(order_data["order_public_id"]), "payment_public_id": str(pay_public_id)}
    
    pay_int_id= await pay_id_by_public_payid(session,pay_public_id)
    create_psp_order = retry_payments(create_psp_order,pay_int_id,session) 
    psp_resp,psp_exc = await create_psp_order(amount_paise=amount_in_paise, currency=currency, 
                                        receipt=receipt, notes=notes,idempotency_key=idempotency_key)
    
    if psp_exc:
        print("psp_exc",psp_exc)
        # await schedule_reconciliation_job(order_public_id=order_data["order_public_id"], payment_attempt_id=res.attempt_id)
        raise HTTPException(status_code=502, detail="Payment provider unreachable;order and payment in pending state")  
    # client will decide how to deal , 
    # client can show pending for some duration to user until not reachable and then give and option to retyr by sending messages like payment is pending
    
    print(psp_resp)
    provider_order_id = psp_resp.get("id") 
    print(provider_order_id)
    if provider_order_id is None:
        pay_status=PaymentAttemptStatus.UNKNOWN.value
        # never got definitive provider response
        # mark attempt as UNKNOWN and schedule background reconciliation
        await record_payment_attempt(
                #** update attempt no to latest attempt plus 1
                session,pay_public_id,DEFAULT_RETRIES+1,pay_status,resp="No provider order id in response")

        # await schedule_reconciliation_job(order_public_id=order_data["order_public_id"], payment_attempt_id=res.attempt_id)
        raise HTTPException(status_code=502, detail="Payment provider unreachable;order and payment in pending state")  
        
        
    # Build a client payload — for UPI you might create deeplink from data or use checkout
    # Example deeplink (merchant VPA must be provided by provider or merchant account)
    #** adjust based on PSP response fields.
    client_payload = {
        "provider": "razorpay",
        "provider_order_id": provider_order_id,
        "provider_raw": psp_resp,
        "checkout_hint": {
            "type": "provider_order",
            "order_id": provider_order_id,
            "note": "Use Razorpay Checkout or construct UPI deeplink / checkout flow using provider SDK",
        },
    }


    # safe to commit payment and idempotency tables separately 
    # as in case of netowrk failures before recording full data in idempotenmcy and on retry razopay will retrun the earlier captured response .

    # update order row
    pay_id=await update_payment_provider_orderid(session,pay_int_id,provider_order_id)
    await session.commit()

    # update idempotency response
    response_body = {
        "order_public_id": str(order_data["order_public_id"]),
        "order_id": order_data["order_id"],
        "payment_public_id": str(pay_public_id),
        "payment_provider_id": str(provider_order_id),
        "payment_client_payload": client_payload,
        "status": "PENDING",
        "message": "Provider order created; client should open provider checkout/deeplink.",
    }
    await update_idempotent_response(session, idempotency_key, 200, response_body)
    await session.commit()
    return response_body
    

    

def retry_payments(func,payment_id,session,max_retries: int = DEFAULT_RETRIES,backoff_base: int = DEFAULT_BACKOFF_BASE):
    async def retry_wrapper(*args, **kwargs):
        last_exc: Optional[Exception] = None
        for attempt_idx in range(1, max_retries + 1):
            pay_status = PaymentAttemptStatus.FIRSTATTEMPT.value
            attempt_id=await record_payment_attempt(
                session,payment_id,attempt_idx,pay_status,resp=None)

            try:
                
                resp = await func(*args, **kwargs)
                print("here")
                if attempt_idx == 1 :
                    raise httpx.ConnectError(message="connect err ")
                print("resp",resp)
                await update_payment_attempt_resp(
                    session,attempt_id,PaymentAttemptStatus.SUCCESS.value,resp)
                
                return resp,None
            except TRANSIENT_EXCEPTIONS as ex:
                # transient network error — mark attempt as retrying, record last_exc, retry
                await update_payment_attempt_resp(
                    session,attempt_id,PaymentAttemptStatus.RETRYING.value,str(ex))
                last_exc = ex
            except httpx.HTTPStatusError as ex:
                # inspect status code
                status_code = ex.response.status_code if ex.response is not None else None
                body_text = ex.response.text if ex.response is not None else str(ex)
               
                if status_code and 500 <= status_code < 600:
                    # server error at provider -> retry
                    await update_payment_attempt_resp(
                    session,attempt_id,PaymentAttemptStatus.RETRYING.value,
                    {"http_status": status_code, "body": f"5xx: {body_text}"})
                    last_exc = ex
                else:
                    # 4xx or other non-retryable -> surface immediately
                    await update_payment_attempt_resp(
                    session,attempt_id,PaymentAttemptStatus.FAILED.value,
                    {"http_status": status_code, "body": f"4xx: {body_text}"})

                    return None, ex
            except Exception as ex:
                # unknown exception -> treat as transient/ambiguous, don't retry
                await update_payment_attempt_resp(
                    session,attempt_id,PaymentAttemptStatus.FAILED.value,
                    str(ex))
                return None , ex
                # last_exc = ex

            # backoff before next try
            await asyncio.sleep(min(backoff_base * (2 ** (attempt_idx - 1)), 8.0))
        return None, last_exc

    
    return retry_wrapper

async def verify_razorpay_signature(request: Request, body: bytes):
    sig = request.headers.get("X-Razorpay-Signature")
    print("sig",sig)
    if not sig:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing signature")
    expected = hmac.new(RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(status_code=400, detail="invalid signature")


async def webhook_event_already_processed(session, provider_event_id: str , provider ) -> bool:
    stmt = select(PaymentWebhookEvent.id,PaymentWebhookEvent.processed_at).where(
        PaymentWebhookEvent.provider == provider,
        PaymentWebhookEvent.provider_event_id == provider_event_id)
    res = await session.execute(stmt)
    ev = res.one_or_none()
    if ev and ev[1] is not None:
        return True
    return False


async def mark_webhook_received(session, provider_event_id: str, provider: str, payload: dict):
    
    try:
        stmt = pg_insert(PaymentWebhookEvent).values(
            provider=provider,
            provider_event_id=provider_event_id,
            payload=payload,
            attempts=1,
            status=PaymentEventStatus.RECEIVED.value,
            created_at=now()
        ).on_conflict_do_nothing(
            constraint="uq_provider_event"
        ).returning(PaymentWebhookEvent.id)
        result = await session.execute(stmt)
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Failed to record webhook event: {str(e)}"
        )

    ev_id = result.scalar_one_or_none()

    if ev_id is not None:
        await session.commit()
        return ev_id
    else:
        stmt = update(PaymentWebhookEvent
                       ).where(PaymentWebhookEvent.provider_event_id == provider_event_id,
                       PaymentWebhookEvent.processed_at.is_(None)).values(
                       attempts=PaymentWebhookEvent.attempts + 1
                       ).returning(PaymentWebhookEvent.id)
        res = await session.execute(stmt)
        ev_id = res.scalar_one_or_none()
        return ev_id

async def mark_webhook_processed(session, ev_id,status: str, last_error: Optional[str] = None):
   
    stmt = (
        update(PaymentWebhookEvent)
        .where(PaymentWebhookEvent.id == ev_id)
        .values(processed_at=now(),
                status=status,
                last_error=last_error)
    )
    await session.execute(stmt)


async def load_order_items_pid_qty(session, order_id: int):
  
    stmt = select(OrderItem.product_id, OrderItem.quantity).where(OrderItem.order_id == order_id)
    res = await session.execute(stmt)
    rows = res.all()
    return [{"product_id": int(r[0]), "quantity": int(r[1])} for r in rows]





