
from fastapi import APIRouter



webhooks_router=APIRouter()


@webhooks_router.post("/payment")
async def payment_status_webhook():
    pass
    # mark payment done & order confirmed in db 
    # enqueue an event of order confirmation and push event to queue 

