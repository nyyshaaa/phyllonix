# outbox_publisher_orm_sqlmodel.py
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, List, Optional, Tuple

from sqlalchemy import select, func, or_, and_, update
from sqlalchemy.exc import SQLAlchemyError

from backend.common.utils import now
from backend.schema.full_schema import OutboxEvent, OutboxEventStatus 

logger = logging.getLogger("outbox.publisher")

DEFAULT_BATCH = 10
DEFAULT_POLL_SECONDS = 1.0
DEFAULT_LOCK_SECONDS = 60
MAX_PUBLISH_ATTEMPTS = 6
BACKOFF_BASE = 5.0


def compute_backoff(attempt: int, base: float = BACKOFF_BASE, cap: float = 3600.0) -> float:
    sec = base * (2 ** (attempt - 1))
    return min(sec, cap)


class OutboxPublisher:

    def __init__(
        self,
        session_factory: Callable[[], Any],
        pubsub,
        *,
        batch_size: int = DEFAULT_BATCH,
        poll_interval: float = DEFAULT_POLL_SECONDS,
        lock_seconds: int = DEFAULT_LOCK_SECONDS,
        max_attempts: int = MAX_PUBLISH_ATTEMPTS,
    ):
        self.session_factory = session_factory
        self.pubsub = pubsub
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self.lock_seconds = lock_seconds
        self.max_attempts = max_attempts
        self._stop = False

    def stop(self):
        self._stop = True

    async def run(self):
        logger.info("OutboxPublisher starting")
        while not self._stop:
            try:
                await self._process_batch()
                
            except Exception:
                logger.exception("OutboxPublisher main loop error; sleeping before retry")
                await asyncio.sleep(self.poll_interval)
        logger.info("OutboxPublisher stopped")

    async def _process_batch(self) -> bool:

        now_expr = now()

        async with self.session_factory() as session:
            # Claim transaction: select & mark lease (use FOR UPDATE SKIP LOCKED)
            async with session.begin():
                # Build the predicate:
                pending_cond = and_(
                    OutboxEvent.status == OutboxEventStatus.PENDING.value,
                    or_(OutboxEvent.next_retry_at == None, OutboxEvent.next_retry_at <= now_expr),
                )

                # Rows that can be reclaimed if locked_until is in the past (stale)
                reclaimable_cond = and_(
                    OutboxEvent.locked_until != None,
                    OutboxEvent.locked_until <= now_expr,
                    OutboxEvent.status != OutboxEventStatus.FAILED.value,
                )

                stmt = (
                    select(
                        OutboxEvent.id,
                        OutboxEvent.topic,
                        OutboxEvent.payload,
                        OutboxEvent.attempts,
                        OutboxEvent.next_retry_at,
                        OutboxEvent.locked_until,
                        OutboxEvent.status,
                    )
                    .where(or_(pending_cond, reclaimable_cond))
                    .order_by(OutboxEvent.id)
                    .limit(self.batch_size)
                    .with_for_update(skip_locked=True)
                )

                res = await session.execute(stmt)
                rows: List[Tuple] = res.all()

                if not rows:
                    return False
                
                lease_until = datetime.now(timezone.utc) + timedelta(seconds=self.lock_seconds)
                # update rows' locked_until using ORM update to avoid loading full objects
                claimed_ids = [r[0] for r in rows]
                await session.execute(
                    update(OutboxEvent)
                    .where(OutboxEvent.id.in_(claimed_ids))
                    .values(locked_until=lease_until)
                )
                # commit claim by leaving the transaction context

        # Process each claimed row (outside claim transaction)
        for r in rows:
            outbox_id = int(r[0])
            topic = r[1]
            payload = r[2]
            attempts = int(r[3] or 0)

            # normalize payload if necessary (Postgres JSONB -> python dict; may already be dict)
            payload_obj = payload
            if isinstance(payload, str):
                try:
                    payload_obj = json.loads(payload)
                except Exception:
                    payload_obj = payload

            try:
                # publish to pubsub (fast-path). pubsub.publish should be async.
                message = {"outbox_id": outbox_id, "payload": payload_obj}
                broker_msg_id = await self.pubsub.publish(topic, message)

                # mark as SENT (we use SENT to indicate broker accepted; worker may later mark DONE)
                async with self.session_factory() as session:
                    async with session.begin():
                        await session.execute(
                            update(OutboxEvent)
                            .where(OutboxEvent.id == outbox_id)
                            .values(
                                status=OutboxEventStatus.SENT.value,
                                sent_at=datetime.now(timezone.utc),
                                locked_until=None,
                                # store broker_msg_id if useful
                                # broker_msg_id=str(broker_msg_id) if broker_msg_id is not None else None
                            )
                        )
            except Exception as ex:
                attempts += 1
                if attempts >= self.max_attempts:
                    logger.exception("Outbox publish failed permanently outbox_id=%s attempts=%d", outbox_id, attempts)
                    async with self.session_factory() as session:
                        async with session.begin():
                            await session.execute(
                                update(OutboxEvent)
                                .where(OutboxEvent.id == outbox_id)
                                .values(status=OutboxEventStatus.FAILED.value, attempts=attempts, locked_until=None, next_retry_at=None)
                            )
                    #  alert / notify ops here if desired
                else:
                    backoff = compute_backoff(attempts)
                    next_at = datetime.now(timezone.utc) + timedelta(seconds=backoff)
                    logger.warning(
                        "Outbox publish failed outbox_id=%s attempt=%d will retry after %.1fs: %s",
                        outbox_id,
                        attempts,
                        backoff,
                        ex,
                    )
                    async with self.session_factory() as session:
                        async with session.begin():
                            await session.execute(
                                update(OutboxEvent)
                                .where(OutboxEvent.id == outbox_id)
                                .values(attempts=attempts, next_retry_at=next_at, locked_until=None, status=OutboxEventStatus.PENDING.value)
                            )

       
