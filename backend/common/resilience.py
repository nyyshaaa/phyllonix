import asyncio
import time
from typing import Optional

class CircuitOpenError(RuntimeError):
    pass


class CircuitBreaker:
    """
    Simple async circuit breaker (in-memory). 
    - failure_threshold: # consecutive failures before opening.
    - recovery_timeout: seconds to wait before allowing a trial (half-open).
    """
     
    def __init__(self, name: str, failure_threshold: int = 3, recovery_timeout: float = 10.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._fail_count = 0
        self._state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self._opened_at: Optional[float] = None
        self._lock = asyncio.Lock()


    async def _maybe_transition(self):
        if self._state == "OPEN" and self._opened_at is not None:
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                self._state = "HALF_OPEN"

    async def before_call(self):
        async with self._lock:
            await self._maybe_transition()

            if self.state == "OPEN":
                raise CircuitOpenError(f"circuit {self.name} is open")
            
            # if HALF_OPEN or CLOSED we allow the call to proceed
            

    async def after_call(self,success:bool):
        async with self._lock:

            # if success make it closed
            if success:
                self._fail_count=0
                self._state="CLOSED"
                self._opened_at=None
                return 
            
            # failure path 
            self._fail_count+=1
            # if we're in HALF_OPEN, a single failing probe re-opens immediately
            if self._fail_count>=self.failure_threshold or self._state == "HALF_OPEN":
                self._state="OPEN"
                self._opened_at=time.monotonic()
                self._fail_count = 0
            



    
    

     
