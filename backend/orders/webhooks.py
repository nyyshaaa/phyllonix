
import json
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import  AsyncSession

from backend.db.dependencies import get_session
from backend.config.settings import config_settings
from backend.orders.services import mark_webhook_processed, mark_webhook_received, update_order_place_npay_states, verify_razorpay_signature, webhook_event_already_processed


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
    if await webhook_event_already_processed(session, provider_event_id):
        return Response(content={"status": "ok", "note": "already processed"},status_code=200)
    
    ev = await mark_webhook_received(session, provider_event_id, provider, payload)

    # process the event
    # Extract payment entity safely (Razorpay payload nests under payload.payment.entity)
    payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {}) or {}
    provider_payment_id = payment_entity.get("id") or payment_entity.get("payment_id")
    psp_pay_status = payment_entity.get("status")  # e.g., 'captured', 'failed', 'authorized'

    # If it's not a payment event, can ignore or handle other events (order.paid etc)
    if not provider_payment_id:
        # mark processed to stop retries
        await mark_webhook_processed(session, ev)
        return Response(content={"status": "ok", "note": "no payment entity"},status_code=200)
    
    update_status = await update_order_place_npay_states(session,provider_payment_id,ev,psp_pay_status)

    #** emit events for shiipin , email confiemation , cart updates etc .
    return update_status
    


   