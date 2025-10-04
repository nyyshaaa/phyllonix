

from fastapi import APIRouter

orders_router=APIRouter()

# create order draft 
@orders_router.post("/checkout")
async def initiate_buy_now():
    pass

# client should get the order id recived from buy now ,store it and ask to user for payment options in ui
# if client proceeds with pay now call get order draft 
# when clicked on pay now call this 
@orders_router.get("/checkout/{order_public_id}/order-draft")
async def get_order_draft(order_public_id:str):
    pass


# after getting order draft client should show payment button(e.g. pay with upi)
# when clicked on proceed to pay call this 
@orders_router.get("/{order_public_id}/secure-payment-init")
async def get_order_draft(order_public_id:str):
    pass

# ----------------------------------------------------------------------------------------------------
# after payment success payment provider api will send a webhook to our server 
# -- next in webhooks file
# ----------------------------------------------------------------------------------------------------

@orders_router.get()
async def get_all_orders():
    pass




