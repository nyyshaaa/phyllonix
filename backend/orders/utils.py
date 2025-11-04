


from datetime import timedelta

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
