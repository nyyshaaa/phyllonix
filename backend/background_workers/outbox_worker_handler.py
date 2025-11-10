

from typing import Any, Dict

from sqlalchemy import update
from backend.common.utils import now
from backend.db.connection import async_session
from backend.__init__ import logger
from backend.orders.repository import  sim_emit_outbox_event
from backend.schema.full_schema import OutboxEvent, OutboxEventStatus

class OrdersOutboxHandler:
    def __init__(self):
        self.async_session = async_session
    
    async def outbox_handler(self,task_data,w_name):

        payload = task_data.get("payload")
        outbox_event_id = task_data.get("outbox_event_id")
        topic = task_data.get("topic")
        order_id = payload.get("order_id")
        logger.info("[%s] processing order_finalize_otbox_event=%s", w_name, outbox_event_id)


        async with async_session() as session:
           
            if topic == "order.paid":

                async with session.begin():
                    # record a received-for-fulfillment outbox event (durable) — optional but useful
                    await sim_emit_outbox_event(session,
                                            topic="order.received_for_fulfillment",
                                            payload={"order_id": order_id},
                                            aggregate_type="order",
                                            aggregate_id=order_id,)
                    
                    await session.execute(
                        update(OutboxEvent).where(OutboxEvent.id == outbox_event_id).values(status=OutboxEventStatus.DONE.value, updated_at=now())
                    )
               

            elif topic == "order.payment_failed":
                async with session.begin():
                    # inventory will automatically expire in some time so no need to chnage that and since order is not placed so no need to decrease stock 
                    await sim_emit_outbox_event(session,
                                            topic="order.payment_failed.notify",
                                            payload={"order_id": order_id, "reason": payload.get("reason")},
                                            aggregate_type="order",
                                            aggregate_id=order_id,)
                    
                    await session.execute(
                        update(OutboxEvent).where(OutboxEvent.id == outbox_event_id).values(status=OutboxEventStatus.DONE.value, updated_at=now())
                    )


   