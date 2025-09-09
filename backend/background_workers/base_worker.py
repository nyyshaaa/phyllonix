
import asyncio
from typing import Any, Dict, List, Optional
from backend.__init__ import logger
from backend.background_workers.thumbnail_worker import ThumbnailTaskHandler

SENTINEL = None  # queue sentinel

class BaseWorker():
    def __init__(self, workers_count:int=2,max_queue_size: int = 1000):
        self.queue: asyncio.Queue[Optional[Dict[str, Any]]] = asyncio.Queue(maxsize=max_queue_size)
        self.worker_loops:Dict[str, asyncio.Task] = {} 
        self.workers_count:int=workers_count
        self._processed = 0
    
    async def __call__(self):
        if not self.worker_loops:
            for i in range(self.workers_count):
                cur_worker_name=f"Worker:{i+1}"
                worker_loop=asyncio.create_task(self._worker_loop(cur_worker_name))
                logger.info("[%s] started", cur_worker_name)

                self.worker_loops[cur_worker_name]=worker_loop


    # def start(self):
    #     """Start the worker loop as a Task on the current event loop."""
    #     if self._task is None:
    #         self._task = asyncio.create_task(self._worker_loop())
    #         logger.info("[%s] started", self.name)

    async def stop(self):
        """Send a sentinel to ask the worker to exit."""
        for i in range(self.workers_count):
            await self.queue.put(None)

    async def shutdown(self, *, drain_first: bool = True, drain_timeout: float = 30.0, wait_timeout: float = 30.0):
        """
        Graceful stop: optionally wait for queue to drain, then send sentinel and await the task.
        """
        if drain_first:
            try:
                await asyncio.wait_for(self.queue.join(), timeout=drain_timeout)
                logger.debug("[%s] queue drained")
            except asyncio.TimeoutError:
                logger.warning("[%s] timeout waiting for queue to drain")

        # send sentinel
        await self.stop()

        for w in self.worker_loops:
            try:
                await asyncio.wait_for(w, timeout=wait_timeout)
            except asyncio.TimeoutError:
                logger.warning("[%s] worker did not finish; cancelling", w["cur_worker_name"])
                w.cancel()
                try:
                    await asyncio.wait_for(w, timeout=5.0)
                except Exception:
                    logger.exception("[%s] worker did not stop after cancel", w["cur_worker_name"])

    async def _worker_loop(self,cur_worker_name):
        """Internal loop. Calls `task_executor()` for each non-sentinel task."""
        logger.info("[%s] loop running", cur_worker_name)
        while True:
            qitem = await self.queue.get()
            try:
                if qitem is None:
                    logger.info("[%s] sentinel received; exiting loop", cur_worker_name)
                    break

                try:
                    # call the concrete task handler (should be async)
                    await self.task_executor(qitem,cur_worker_name)
                except Exception:
                    logger.exception("[%s] handler threw for task: %s", cur_worker_name, qitem)
            finally:
                # ALWAYS mark done for each get()
                try:
                    self.queue.task_done()
                except Exception:
                    logger.exception("[%s] queue.task_done() failed", cur_worker_name)

        logger.info("[%s] exiting", cur_worker_name)

   
    async def task_executor(self, task: Dict[str, Any],wname) -> Optional[int]:
       
        if task["event"]=="image_uploaded":
            thumbnail_task_handler=ThumbnailTaskHandler()
            await thumbnail_task_handler.thumbgen(task["data"],wname)
            await thumbnail_task_handler.log_analytics()
            await thumbnail_task_handler.notify_admin()
            
    


