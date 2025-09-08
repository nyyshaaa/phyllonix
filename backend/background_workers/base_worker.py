
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from backend.__init__ import logger

SENTINEL = None  # queue sentinel

class BaseWorker(ABC):
    def __init__(self, name: str, max_queue_size: int = 1000):
        self.name = name
        self.queue: asyncio.Queue[Optional[Dict[str, Any]]] = asyncio.Queue(maxsize=max_queue_size)
        self._task: Optional[asyncio.Task] = None
        self._processed = 0

    def start(self):
        """Start the worker loop as a Task on the current event loop."""
        if self._task is None:
            self._task = asyncio.create_task(self._worker_loop())
            logger.info("[%s] started", self.name)

    async def stop(self):
        """Send a sentinel to ask the worker to exit."""
        await self.queue.put(None)

    async def shutdown(self, *, drain_first: bool = True, drain_timeout: float = 30.0, wait_timeout: float = 30.0):
        """
        Graceful stop: optionally wait for queue to drain, then send sentinel and await the task.
        """
        if drain_first:
            try:
                await asyncio.wait_for(self.queue.join(), timeout=drain_timeout)
                logger.debug("[%s] queue drained", self.name)
            except asyncio.TimeoutError:
                logger.warning("[%s] timeout waiting for queue to drain", self.name)

        # send sentinel
        await self.stop()

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=wait_timeout)
            except asyncio.TimeoutError:
                logger.warning("[%s] worker did not finish; cancelling", self.name)
                self._task.cancel()
                try:
                    await asyncio.wait_for(self._task, timeout=5.0)
                except Exception:
                    logger.exception("[%s] worker did not stop after cancel", self.name)

    async def _worker_loop(self):
        """Internal loop. Calls `task_executor()` for each non-sentinel task."""
        logger.info("[%s] loop running", self.name)
        while True:
            qitem = await self.queue.get()
            try:
                if qitem is None:
                    logger.info("[%s] sentinel received; exiting loop", self.name)
                    break

                try:
                    # call the concrete task handler (should be async)
                    res = await self.task_executor(qitem)
                    if isinstance(res, int):
                        self._processed += res
                except Exception:
                    logger.exception("[%s] handler threw for task: %s", self.name, qitem)
            finally:
                # ALWAYS mark done for each get()
                try:
                    self.queue.task_done()
                except Exception:
                    logger.exception("[%s] queue.task_done() failed", self.name)

        logger.info("[%s] exiting; processed=%d", self.name, self._processed)

    @abstractmethod
    async def task_executor(self, task: Dict[str, Any]) -> Optional[int]:
        """Implement in subclass. Return int count processed (optional)."""
        raise NotImplementedError
