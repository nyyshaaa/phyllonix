
import json
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import  AsyncSession
from backend.db.dependencies import get_session
from backend.config.settings import config_settings
from backend.orders.repository import emit_outbox_event, update_order_status, update_order_status_get_orderid, update_pay_completion_get_orderid
from backend.orders.services import mark_webhook_processed, mark_webhook_received, verify_razorpay_signature, webhook_event_already_processed
from backend.orders.utils import pay_order_status_util
from backend.schema.full_schema import OrderStatus, PaymentEventStatus


webhooks_router=APIRouter()

@webhooks_router.post("/razorpayy")
async def razorpay_webhook(request: Request, session: AsyncSession = Depends(get_session)):
    body = await request.body()
    
    # verify signature
    await verify_razorpay_signature(request, body)
    print("hereee")
    payload = json.loads(body)
    provider_event_id = request.headers.get("X-Razorpay-Event-Id")

    if not provider_event_id:
        # bad payload; acknowledge to avoid retries or log and 400
        raise HTTPException(status_code=400, detail="missing event id")

    provider = "razorpay"

    # insert/mark webhook receipt (dedupe)
    if await webhook_event_already_processed(session, provider_event_id,provider):
        return {"status": "ok", "note": "already processed"}
    
    ev_id = await mark_webhook_received(session, provider_event_id, provider, payload)

    # process the event
    payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {}) or {}
    provider_payment_id = payment_entity.get("id") or payment_entity.get("payment_id")
    provider_order_id = payment_entity.get("order_id")
    psp_pay_status = payment_entity.get("status")  # e.g., 'captured', 'failed', 'authorized'


    # If it's not a payment event, can ignore or handle other events (order.paid etc)
    if not provider_payment_id:
        # mark processed to stop retries
        await mark_webhook_processed(session, ev_id,status=PaymentEventStatus.IGNORED.value, last_error="no payment entity")
        await session.commit()
        return {"status": "ok", "note": "no payment entity"}
    

    payment_status,order_status,note = pay_order_status_util(psp_pay_status)
    
    
    order_id = await update_pay_completion_get_orderid(session,provider_order_id,provider_payment_id,payment_status)
    if not order_id:
        # If provider_payment exists but we don't have it, store for reconciliation and return 200
        # mark event processed so provider stops retrying
        await mark_webhook_processed(session, ev_id,status=PaymentEventStatus.IGNORED.value, last_error="no pay record found for provider_order_id")
        return {"status": "ok", "note": "payment not found"}
    
    await update_order_status(session,order_id,order_status)

    outbox_payload = {
        "order_id": order_id,
        "payment_provider_id": provider_payment_id,
        "provider_order_id": provider_order_id,
        "raw_payload": payload
    }
    dedupe_key = f"order:{order_id}"
    await emit_outbox_event(session, 
                            topic="order.paid" if order_status == OrderStatus.CONFIRMED.value else "order.payment_failed", 
                            payload=outbox_payload,
                            aggregate_type="order",
                            aggregate_id=order_id,
                            dedupe_key=dedupe_key,)

    
    await mark_webhook_processed(session, ev_id,status=PaymentEventStatus.PROCESSED)
    await session.commit()

    return {"status": "ok", "note": note}
    


   