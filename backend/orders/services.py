

import json
from typing import Optional
from fastapi import HTTPException
import httpx
from backend.orders.repository import items_avblty, update_idempotent_response, update_payment_attempt, update_payment_status
from backend.config.settings import config_settings

PSP_API_BASE=config_settings.RZPAY_GATEWAY_URL
PSP_KEY_ID=config_settings.RZPAY_KEY
PSP_KEY_SECRET=config_settings.RZPAY_SECRET


async def validate_items_avblty(session,cart_items):
    
    product_ids=[]
    product_data={}
    for it in cart_items:
        product_ids.append(it["product_id"])
        product_data[int(it["product_id"])]={
        "stock_qty": int(it["product_stock"]),
        "requested_qty": int(it["quantity"]),
        }
        

    await items_avblty(session,product_ids,product_data)

#** check the commits placement here
async def create_payment_intent(session,idempotency_key,order_totals,order_data):
    pay_public_id=order_data["pay_public_id"]
    try:
        # amount expected in paise
        amount_in_paise = order_totals["total"]*100
        currency = "INR"
        receipt = f"order_{order_data['order_public_id']}"
        notes = {"order_public_id": order_data["order_public_id"], "payment_public_id": pay_public_id}

        psp_resp = await create_psp_order(amount_paise=amount_in_paise, currency=currency, 
                                          receipt=receipt, notes=notes,idempotency_key=idempotency_key)
        provider_order_id = psp_resp.get("id") 
        if not provider_order_id:
            # fallback: try other keys or treat as error
            raise RuntimeError("Provider did not return order id")   #**recheck
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

        # persist provider id and payment_attempt response & update idempotency table
        # update payment row
        pay_id=update_payment_status(session,pay_public_id,provider_order_id)
        
        # update payment_attempt.provider_response (assume attempt_no=1)
        update_payment_attempt(session,pay_id,psp_resp)

        # update idempotency response
        response_body = {
            "order_public_id": order_data["order_public_id"],
            "order_id": order_data["order_id"],
            "payment_public_id": pay_public_id,
            "payment_provider_id": provider_order_id,
            "payment_client_payload": client_payload,
            "status": "PENDING",
            "message": "Provider order created; client should open provider checkout/deeplink.",
        }
        await update_idempotent_response(session, idempotency_key, 200, response_body)
        return response_body
    except httpx.HTTPError as e:
        # PSP call failed — mark payment attempt as failed and return 502 to client or retry strategy
        # Update payment_attempt to reflect failure and keep idempotency row for retry
        resp=json.dumps({"error": str(e)})
        update_payment_attempt(session,pay_id,resp)
        raise HTTPException(status_code=502, detail="Payment provider error, please retry")
    

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
        headers["Idempotency-Key"] = idempotency_key
    payload = {
        "amount": amount_paise,
        "currency": currency,
        "receipt": receipt,
        "notes": notes or {},
    }
    async with httpx.AsyncClient(timeout=10.0, auth=(PSP_KEY_ID, PSP_KEY_SECRET)) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data
