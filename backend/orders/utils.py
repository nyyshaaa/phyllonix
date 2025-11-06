


from datetime import timedelta
import hashlib

from sqlalchemy import text

from backend.orders.constants import UPI_RESERVATION_TTL_MINUTES


def compute_order_totals(items,payment_method,checkout_public_id,cs_expires_at):
    # Compute totals
    subtotal = sum(int(it["prod_base_price"]) * int(it["quantity"]) for it in items)
    tax = int(subtotal * 0.02)
    shipping = 50
    discount = 0

    cod_fee = 0
    if payment_method == "COD":
        cod_fee = 50
    total = subtotal + tax + shipping + cod_fee - discount

    # Optionally extend TTL for slower payment methods like UPI
    if payment_method == "UPI":
        cs_expires_at = cs_expires_at + timedelta(minutes=UPI_RESERVATION_TTL_MINUTES)

    
    #** if want to return with response
    # "confirm_instructions": {
        #     "endpoint": f"/checkout/{checkout_public_id}/confirm",
        #     "method": "POST",
        #     "idempotency_required": True,
    # },

    return {
        "checkout_id": str(checkout_public_id),
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


def idempotency_lock_key(ikey: str) -> int:
    h = hashlib.sha256(ikey.encode()).digest()[:8]
    val = int.from_bytes(h, "big", signed=False)
    # convert to signed 64-bit
    if val > (1 << 63) - 1:
        val = val - (1 << 64)
    return val


async def acquire_pglock(session,lock_key):
    got_lock_row = await session.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": lock_key})
    got_lock = bool(got_lock_row.scalar_one())
    return got_lock
    