
import json
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import  AsyncSession
from backend.db.dependencies import get_session
from backend.config.settings import config_settings
from backend.orders.repository import create_commit_intent, emit_outbox_event, get_pay_record_by_provider_orderid, update_order_status, update_pay_completion_get_orderid, webhook_error_recorded
from backend.orders.services import  load_order_items_pid_qty, mark_webhook_processed, mark_webhook_received, verify_razorpay_signature, webhook_event_already_processed
from backend.orders.utils import pay_order_status_util
from backend.schema.full_schema import OrderStatus, PaymentEventStatus, PaymentStatus
from backend.config.admin_config import admin_config
from backend.common.constants import request_id_ctx
from backend.common.retries import is_recoverable_exception
from backend.orders.constants import logger

webhooks_router=APIRouter()

EXPECTED_ENV = admin_config.ENV

async def razorpay_webhook(request: Request, session: AsyncSession = Depends(get_session)):
    print("In razorpay webhook handler")
    body = await request.body()
    app=request.app
    # verify signature ,(save , respond 200 ok to psp and reconcile for errored cases after few retries)
    await verify_razorpay_signature(request, session,body)
    payload = json.loads(body)
    provider_event_id = request.headers.get("X-Razorpay-Event-Id")
    event = payload.get("event")

    if not provider_event_id:
        # bad payload; acknowledge to avoid retries , reconcile 
        #** concurrent requests may here add duplicates but that's okay as we will seprately deal with rows with null provider event id's and earlier pending payment records .
        await mark_webhook_received(session, None, "razorpay", payload, last_error="missing event id",status = PaymentEventStatus.INCONSISTENT.value)
        return JSONResponse({"status": "ok", "note": "ignored: missing event id"}, status_code=200)

    provider = "razorpay"

    # process the event
    payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {}) or {}
    provider_payment_id = payment_entity.get("id") or payment_entity.get("payment_id")
    provider_order_id = payment_entity.get("order_id")
    psp_pay_status = payment_entity.get("status")  # e.g., 'captured', 'failed', 'authorized'

    # to confirm we have a matching payment record(pending state) for provider order id in our system , like to verify that the webhook status is received for a valid payment record .
    pay_record = await get_pay_record_by_provider_orderid(session,provider_order_id,provider)
    print(pay_record)
    order_id = pay_record["order_id"] if pay_record else None
    if not pay_record or not order_id:
        # If provider_payment exists but we don't have it, store for reconciliation and return 200
        # mark event error for reconcile and return 200 to provider
        await mark_webhook_received(session, provider_event_id, "razorpay", payload, last_error="no pay record found for provider_order_id",pay_status = PaymentEventStatus.INCONSISTENT.value)
        return JSONResponse({"status": "ok", "note": "ignored: payment not found"}, status_code=200)

    # If it's not a payment event, can ignore
    if not provider_payment_id:
        await mark_webhook_received(session, provider_event_id, "razorpay", payload, last_error="no provider_payment_id",status = PaymentEventStatus.INCONSISTENT.value)
        # send ok to stop retries and reconcile later
        return JSONResponse({"status": "ok", "note": "ignored: no payment entity"}, status_code=200)
    
    payment_status,final_order_status,is_valid_event,note = pay_order_status_util(psp_pay_status,event)
    ev = await mark_webhook_received(session, provider_event_id, provider, payload,order_id=order_id,pay_status=payment_status)
    if not is_valid_event:
        return JSONResponse({"status": "ok", "note": "ignored: no valid event"}, status_code=200)
    
    if ev is not None and ev["processed_at"] is not None:
        return JSONResponse({"status": "ok", "note": "already processed"}, status_code=200)
    ev_id=ev["id"]
    # critical section , record/update errors safely for easiest reconcilation .
    topic = None
    outbox_event_id = None 
    commit_int_id = None
    
    try:
        
        order_id = await update_pay_completion_get_orderid(session,pay_record["id"],provider_payment_id,payment_status)
        print("Updated payment record , got order id:", order_id)
        # if not order_id:
        #     return JSONResponse({"status": "ok", "note": "event not in order"}, status_code=200)

        await update_order_status(session,order_id,final_order_status)

        if payment_status in (
            PaymentStatus.CAPTURED.value,
            PaymentStatus.FAILED.value,
        ):
            outbox_payload = {
            "order_id": order_id,
            "payment_provider_id": provider_payment_id,
            "provider_order_id": provider_order_id
            }

            topic="order.paid" if payment_status == PaymentStatus.CAPTURED.value else "order.pending_payment" 
            
            commit_int_id =None
            if payment_status == PaymentStatus.CAPTURED.value:
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

        await mark_webhook_processed(session, ev_id)
        await session.commit()

    except Exception as e:
        rid = request_id_ctx.get(None)

        try:
            await session.rollback()
            await webhook_error_recorded(
                session,
                ev_id,
                last_error=(
                    f"error while processing webhook "
                    f"current statuses: (payment_status={payment_status}, order_status={final_order_status})"
                ),
            )
            await session.commit()
        except Exception as rb_err:
            logger.error(
                "razorpay.webhook.record_error_failure",
                exc_info=(type(rb_err), rb_err, rb_err.__traceback__),
                extra={"request_id": rid, "webhook_event_id": ev_id},
            )
        # psp retries non 200's so psp will retry even without reraise , like if we just swallow error and don't retry
        # but to get error trackebacks in logs reraise 
        raise

    if topic and outbox_event_id:
     
        app.state.pubsub_pub(topic, {"outbox_event_id": outbox_event_id, "topic": topic, "payload": outbox_payload})

        if commit_int_id:
          
            # lightweight payload: commit intent id (worker will re-load intent from DB and lock it)
            app.state.pubsub_pub("order_confirm_intent.created", {"commit_intent_id": commit_int_id, "order_id": order_id})

    return JSONResponse({"status": "ok", "note": note}, status_code=200)
    


    