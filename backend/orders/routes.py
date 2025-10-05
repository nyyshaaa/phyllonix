

from fastapi import APIRouter

orders_router=APIRouter()

# in cart (user clicks on procceed to buy)
@orders_router.post("/checkout/initiate")
async def initiate_buy_now():
    pass

# client should get the checkout id recived from initiate_buy_now ,store it and set it in url 
# ask to user for payment options in ui , users can select payment methods 

# when user clicks on proceed with selected payment method 
@orders_router.get("/checkout/{checkout_id}/order-summary")
async def get_order_summary(checkout_id:str):
    pass


# when clicked on proceed to pay with upi etc. call this 
# order creation will happen here in final stage
@orders_router.get("/{checkout_id}/secure-payment-init")
async def place_order_with_pay(checkout_id:str):
    pass

# ----------------------------------------------------------------------------------------------------
# after payment success payment provider api will send a webhook to our server 
# -- next in webhooks file
# ----------------------------------------------------------------------------------------------------

@orders_router.get()
async def get_all_orders():
    pass




