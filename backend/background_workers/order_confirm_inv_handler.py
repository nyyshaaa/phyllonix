
from typing import Any, Dict
from sqlmodel import select, update
from sqlalchemy import text
from datetime import datetime, timedelta
from backend.common.utils import now
from backend.db.connection import async_session
from backend.orders.repository import sim_emit_outbox_event
from backend.schema.full_schema import CommitIntent, CommitIntentStatus, InventoryReservation, InventoryReserveStatus, Product
from backend.__init__ import logger

DEFAULT_MAX_ATTEMPTS = 5

async def order_confirm_commitintent_handler(task_data: Dict[str, Any], worker_name: str):
    
    ci_id = task_data.get("commit_intent_id")
    if not ci_id:
        logger.info("no commit intent id found returning")
        return

    async with async_session() as session:
        try:
            # acquire and mark PROCESSING (short transaction)
            async with session.begin():
                stmt = select(CommitIntent.status).where(CommitIntent.id == ci_id,
                                                         CommitIntent.status==CommitIntentStatus.PENDING.value).with_for_update(skip_locked=True)
                res = await session.execute(stmt)
                ci_status = res.scalar_one_or_none()
                if not ci_status:
                    logger.info("commit_intent_handler: no CI row for id=%s", ci_id)
                    return

                if ci_status == CommitIntentStatus.DONE.value:
                    logger.info("commit_intent_handler: CI already done id=%s", ci_id)
                    return


                await session.execute(
                    update(CommitIntent)
                    .where(CommitIntent.id == ci_id)
                    .values(status=CommitIntentStatus.PROCESSING.value, attempts=CommitIntent.attempts + 1, updated_at=now())
                )

            # do the heavy transactional work (stock decrement) in a new tx
            async with session.begin():
                stmt = select(CommitIntent.payload, CommitIntent.aggregate_id).where(CommitIntent.id == ci_id).with_for_update()
                res = await session.execute(stmt)
                row = res.one_or_none()
                if not row:
                    raise RuntimeError("commit intent missing payload")

                payload = row[0] or {}
                order_id = payload.get("order_id") or row[1]
                items = payload.get("items") or []

                # validate reservation sums and lock product rows then decrement
                for it in items:
                    pid = int(it["product_id"])
                    qty = int(it["quantity"])
                    
                    # lock product row
                    p_stmt = select(Product).where(Product.id == pid).with_for_update()
                    prod_res = await session.execute(p_stmt)
                    prod = prod_res.scalar_one_or_none()
                    if not prod:
                        raise RuntimeError(f"product not found {pid}")

                    if prod.stock_qty < qty:
                        raise RuntimeError(f"insufficient stock for product {pid}: stock={prod.stock_qty} need={qty}")

                    new_stock = prod.stock_qty - qty
                    await session.execute(
                        update(Product).where(Product.id == pid).values(stock_qty=new_stock, updated_at=now())
                    )

                # mark reservations COMMITTED
                # or leave for now anyway they will get expired in some time 

                # mark commit intent DONE
                await session.execute(
                    update(CommitIntent).where(CommitIntent.id == ci_id).values(status=CommitIntentStatus.DONE.value, updated_at=now())
                )

                # emit outbox events inside same tx
                inv_payload = {"order_id": order_id, "items": items}
                await sim_emit_outbox_event(session, topic="inventory.committed", payload=inv_payload,
                                           aggregate_type="order", aggregate_id=order_id,
                                           dedupe_key=f"inventory.committed:{order_id}")
                await sim_emit_outbox_event(session, topic="order.confirmed", payload={"order_id": order_id},
                                           aggregate_type="order", aggregate_id=order_id,
                                           dedupe_key=f"order.confirmed:{order_id}")

            logger.info("commit_intent_handler: processed CI id=%s order=%s", ci_id, order_id)

        except Exception as exc:
            # schedule retry/backoff or mark failed after N attempts
            logger.exception("commit_intent_handler: failure processing CI %s: %s", ci_id, exc)
            async with async_session() as s2:
                # bump attempts and set next_retry_at (exponential backoff)
                stmt = select(CommitIntent.attempts).where(CommitIntent.id == ci_id)
                r = await s2.execute(stmt)
                attempts = r.scalar_one_or_none() or 0
                if attempts + 1 >= DEFAULT_MAX_ATTEMPTS:
                    await s2.execute(update(CommitIntent).where(CommitIntent.id == ci_id).values(status=CommitIntentStatus.FAILED.value, updated_at=now()))
                else:
                    next_try = now() + timedelta(seconds=min(60 * (2 ** attempts), 3600))
                    await s2.execute(update(CommitIntent).where(CommitIntent.id == ci_id).values(status=CommitIntentStatus.PENDING.value, next_retry_at=next_try, attempts=CommitIntent.attempts + 1))
                await s2.commit()
            return
