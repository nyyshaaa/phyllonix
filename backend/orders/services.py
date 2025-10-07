

from backend.orders.repository import items_avblty


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