

from backend.orders.repository import items_avblty


async def validate_items_avblty(session,cart_items):
    
    product_ids=[]
    product_qts=[]
    requested_qts=[]
    for it in cart_items:
        product_ids.append(it["product_id"])
        product_qts.append(it["product_stock"])
        requested_qts.append(it["quantity"])

    await items_avblty(session, product_ids,product_qts,requested_qts)