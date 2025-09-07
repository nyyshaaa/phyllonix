
# backend/exit_workers.py
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class ExitBgWorkers:
    def __init__(self,
                 queue: asyncio.Queue,
                 worker_loop: Optional[asyncio.Task],
                 num_consumers: int = 1,
                 drain_timeout: float = 30.0,
                 worker_wait_timeout: float = 30.0,
                 join_timeout: float = 5.0):
        self.queue = queue
        self.worker_loop = worker_loop
        self.num_consumers = max(1, num_consumers)
        self.drain_timeout = drain_timeout
        self.worker_wait_timeout = worker_wait_timeout
        self.join_timeout = join_timeout

    async def drain_queue(self) -> None:
        """Wait for the queue to be processed (task_done called for each item)."""
        try:
            await asyncio.wait_for(self.queue.join(), timeout=self.drain_timeout)
            logger.debug("Queue drained")
        except asyncio.TimeoutError:
            logger.warning("Timeout while waiting for queue to drain; proceeding to send sentinels")

    async def send_sentinels(self) -> None:
        """Send one sentinel (None) per consumer to signal graceful exit."""
        for _ in range(self.num_consumers):
            await self.queue.put(None)
        logger.debug("Sentinels sent (%d)", self.num_consumers)

    async def wait_for_worker(self) -> None:
        """Wait for worker task to finish; cancel if it times out."""
        if not self.worker_loop:
            return

        try:
            await asyncio.wait_for(self.worker_loop, timeout=self.worker_wait_timeout)
            logger.debug("Worker finished cleanly")
        except asyncio.TimeoutError:
            logger.warning("Worker did not finish in time; cancelling")
            self.worker_loop.cancel()
            try:
                await asyncio.wait_for(self.worker_loop, timeout=self.join_timeout)
            except Exception:
                logger.exception("Worker did not shut down after cancellation")

    async def shutdown(self, *, drain_first: bool = True) -> None:
        """
        Orchestrates graceful shutdown.
        - drain_first=True: wait for queue.join(), then send sentinels.
        - drain_first=False: send sentinels first (use only if you know producers stopped).
        """
        if drain_first:
            await self.drain_queue()

        # now tell consumers to stop
        await self.send_sentinels()

        # wait for consumers to exit
        await self.wait_for_worker()

        # optionally ensure queue is drained of any leftover items that may have been added
        # (use a short timeout to avoid hangs)
        try:
            await asyncio.wait_for(self.queue.join(), timeout=self.join_timeout)
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for queue.join() after sentinels")
