

import asyncio
import hashlib
import hmac
import json
import uuid
from typing import Optional
from fastapi import HTTPException, Request, Response , status
from fastapi.responses import JSONResponse
import httpx
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from backend.common.utils import now
from backend.orders.repository import items_avblty, record_payment_attempt, update_idempotent_response, update_payment_attempt_resp, update_payment_status_nprovider
from backend.config.settings import config_settings
from backend.schema.full_schema import OrderItem, Orders, OrderStatus, Payment, PaymentAttempt, PaymentAttemptStatus, PaymentEventStatus, PaymentStatus, PaymentWebhookEvent
from sqlalchemy.dialects.postgresql import insert as pg_insert
from backend.config.admin_config import admin_config
from backend.orders.constants import logger

PSP_API_BASE=config_settings.RZPAY_GATEWAY_URL
PSP_KEY_ID=config_settings.RZPAY_KEY
PSP_KEY_SECRET=config_settings.RZPAY_SECRET
RAZORPAY_WEBHOOK_SECRET=config_settings.RAZORPAY_WEBHOOK_SECRET
TRANSIENT_EXCEPTIONS = (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.NetworkError)
DEFAULT_RETRIES=3
DEFAULT_BACKOFF_BASE = 0.5 

current_env = admin_config.ENV

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

    print("psp call")
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
    psp_resp,psp_non_retryable_exc,psp_retryable_exc,current_attempt_no= await create_psp_order(amount_paise=amount_in_paise, currency=currency, 
                                        receipt=receipt, notes=notes,idempotency_key=idempotency_key)
    
    if psp_non_retryable_exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Payment attempts failed due to {psp_non_retryable_exc}")  
   
    if psp_retryable_exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Payment failed due to {psp_retryable_exc}")  

    provider_order_id = psp_resp.get("id") 
    if provider_order_id is None:
        pay_status=PaymentAttemptStatus.UNKNOWN.value
        # never got definitive provider response
        # mark attempt as UNKNOWN and schedule background reconciliation
        attempt_id = await record_payment_attempt(
                session,pay_int_id,current_attempt_no+1,pay_status,resp="No provider order id in response")

        # await schedule_reconciliation_job(order_public_id=order_data["order_public_id"], payment_attempt_id=attempt_id)
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

    # update order row
    pay_id=await update_payment_status_nprovider(session,pay_int_id,provider_order_id)

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
        non_retryable_exc=None
        retryable_exc=None
        for attempt_idx in range(1, max_retries + 1):
            pay_status = PaymentAttemptStatus.PENDING.value
            attempt_id=await record_payment_attempt(
                session,payment_id,attempt_idx,pay_status,resp=None)

            try:
                
                resp = await func(*args, **kwargs)
                await update_payment_attempt_resp(
                    session,attempt_id,PaymentAttemptStatus.SUCCESS.value,resp)
                
                return resp,None,None,attempt_idx
            except TRANSIENT_EXCEPTIONS as ex:
                # transient network error — mark attempt as retrying, retry
                retryable_exc = ex
                await update_payment_attempt_resp(
                    session,attempt_id,PaymentAttemptStatus.RETRYING.value,str(ex))
            except httpx.HTTPStatusError as ex:
                # inspect status code
                status_code = ex.response.status_code if ex.response is not None else None
                body_text = ex.response.text if ex.response is not None else str(ex)
               
                if status_code and 500 <= status_code < 600:
                    # server error at provider -> retry
                    retryable_exc = ex
                    await update_payment_attempt_resp(
                    session,attempt_id,PaymentAttemptStatus.RETRYING.value,
                    {"http_status": status_code, "body": f"5xx: {body_text}"})
                else:
                    # 4xx or other non-retryable -> surface immediately
                    non_retryable_exc = ex
                    await update_payment_attempt_resp(
                    session,attempt_id,PaymentAttemptStatus.FAILED.value,
                    {"http_status": status_code, "body": f"4xx: {body_text}"})

                    return None, non_retryable_exc,retryable_exc,attempt_idx
            except Exception as ex:
                # unknown exception -> treat as transient/ambiguous, don't retry
                non_retryable_exc = ex
                await update_payment_attempt_resp(
                    session,attempt_id,PaymentAttemptStatus.FAILED.value,
                    str(ex))
                return None , non_retryable_exc,retryable_exc,attempt_idx

            # backoff before next try
            await asyncio.sleep(min(backoff_base * (2 ** (attempt_idx - 1)), 8.0))
        return None, non_retryable_exc,retryable_exc,max_retries

    return retry_wrapper

async def verify_razorpay_signature(request: Request, session, body: bytes):
    sig = request.headers.get("X-Razorpay-Signature")
    if not sig:
        logger.error("razorpay_webhook.missing_signature")
        await mark_webhook_received(session, None, "razorpay", None, last_error="rzpay_missing_signature",status = PaymentEventStatus.INCONSISTENT.value)
        raise HTTPException(status_code=200, detail="ignored: missing signature")
    expected = hmac.new(RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        logger.error("razorpay_webhook.invalid_signature")
        await mark_webhook_received(session, None, "razorpay", None, last_error="rzpay_invalid_signature",status=PaymentEventStatus.INCONSISTENT.value)
        raise HTTPException(status_code=200, detail="ignored: invalid signature")
    

async def webhook_event_already_processed(session, provider_event_id: str , provider ) -> bool:
    stmt = select(PaymentWebhookEvent.id,PaymentWebhookEvent.processed_at).where(
        PaymentWebhookEvent.provider == provider,
        PaymentWebhookEvent.provider_event_id == provider_event_id)
    res = await session.execute(stmt)
    ev = res.one_or_none()
    if ev and ev[1] is not None:
        return True
    return False

 
async def mark_webhook_received(session,provider_event_id: Optional[str], provider: str, payload: dict ,
                                    order_id:Optional[int]=None,last_error: Optional[str] = None, pay_status:Optional[str]=None ) -> Optional[int]:
    
   
    stmt = pg_insert(PaymentWebhookEvent).values(
        provider=provider,
        provider_event_id=provider_event_id,
        order_id=order_id,
        payload=payload,
        attempts=1,
        status= pay_status or PaymentEventStatus.RECEIVED.value,
        last_error=last_error,
        created_at=now()
    ).on_conflict_do_nothing(
        index_elements=["provider", "provider_event_id"],
        index_where=text("provider_event_id IS NOT NULL"),
    ).returning(PaymentWebhookEvent.id,PaymentWebhookEvent.processed_at)
    result = await session.execute(stmt)
    ev = result.one_or_none()
    if ev is None:
        return None
    return {"id":ev[0],"processed_at":ev[1]}


async def mark_webhook_processed(session, ev_id,last_error: Optional[str] = None):
   
    stmt = (
        update(PaymentWebhookEvent)
        .where(PaymentWebhookEvent.id == ev_id)
        .values(processed_at=now(),
                last_error=last_error)
    )
    await session.execute(stmt)

async def load_order_items_pid_qty(session, order_id: int):
  
    stmt = select(OrderItem.product_id, OrderItem.quantity).where(OrderItem.order_id == order_id)
    res = await session.execute(stmt)
    rows = res.all()
    return [{"product_id": int(r[0]), "quantity": int(r[1])} for r in rows]





