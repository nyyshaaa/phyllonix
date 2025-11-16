
import json
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import  AsyncSession
from backend.db.dependencies import get_session
from backend.config.settings import config_settings
from backend.orders.repository import create_commit_intent, emit_outbox_event, update_order_status, update_pay_completion_get_orderid
from backend.orders.services import  load_order_items_pid_qty, mark_webhook_processed, mark_webhook_received, verify_razorpay_signature, webhook_event_already_processed
from backend.orders.utils import pay_order_status_util
from backend.schema.full_schema import OrderStatus, PaymentEventStatus


webhooks_router=APIRouter()

@webhooks_router.post("/razorpayy")
async def razorpay_webhook(request: Request, session: AsyncSession = Depends(get_session)):
    body = await request.body()
    app=request.app
    # verify signature
    await verify_razorpay_signature(request, body)
    print("hereee")
    payload = json.loads(body)
    provider_event_id = request.headers.get("X-Razorpay-Event-Id")

    if not provider_event_id:
        # bad payload; acknowledge to avoid retries , reconcile 
        return JSONResponse({"status": "ok", "note": "ignored: missing event id"}, status_code=200)

    provider = "razorpay"

    # insert/mark webhook receipt (dedupe)
    if await webhook_event_already_processed(session, provider_event_id,provider):
        return JSONResponse({"status": "ok", "note": note}, status_code=200)
    
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
        return JSONResponse({"status": "ok", "note": "ignored: no payment entity"}, status_code=200)
    
    payment_status,order_status,note = pay_order_status_util(psp_pay_status)
    
    order_id = await update_pay_completion_get_orderid(session,provider_order_id,provider_payment_id,payment_status)
    if not order_id:
        # If provider_payment exists but we don't have it, store for reconciliation and return 200
        # mark event processed so provider stops retrying
        await mark_webhook_processed(session, ev_id,status=PaymentEventStatus.IGNORED.value, last_error="no pay record found for provider_order_id")
        return JSONResponse({"status": "ok", "note": "ignored: payment not found"}, status_code=200)
    
    await update_order_status(session,order_id,order_status)

    outbox_payload = {
        "order_id": order_id,
        "payment_provider_id": provider_payment_id,
        "provider_order_id": provider_order_id,
        "raw_payload": payload
    }
    topic="order.paid" if order_status == OrderStatus.CONFIRMED.value else "order.payment_failed" 
    
    commit_int_id =None
    if order_status == OrderStatus.CONFIRMED.value:
            # build commit payload: items & quantities from order_items
            items = await load_order_items_pid_qty(session, order_id)  # returns list of {product_id, qty}
            commit_payload = {"order_id": order_id, "items": items}
            # create commit intent (idempotent: do not duplicate if exists)
            commit_int_id = await create_commit_intent(session, order_id, "payment_succeeded", aggr_type = "order",payload = commit_payload)
    
    outbox_event_id = await emit_outbox_event(session, 
                            topic=topic, 
                            payload=outbox_payload,
                            aggregate_type="order",
                            aggregate_id=order_id,)

                
    await mark_webhook_processed(session, ev_id,status=PaymentEventStatus.PROCESSED)
    await session.commit()

    app.state.pubsub_pub(topic, {"outbox_event_id": outbox_event_id, "topic": topic, "payload": outbox_payload})

    if commit_int_id:
        # lightweight payload: commit intent id (worker will re-load intent from DB and lock it)
        app.state.pubsub_pub("order_confirm_intent.created", {"commit_intent_id": commit_int_id, "order_id": order_id})

    return JSONResponse({"status": "ok", "note": note}, status_code=200)
    


   