# utils/circuit.py
import asyncio
import time
from typing import Optional

class CircuitOpenError(RuntimeError):
    pass

class CircuitBreaker:
    """
    Simple async in-memory circuit breaker.

    Usage:
      cb = CircuitBreaker(name="postgres", failure_threshold=3, recovery_timeout=30, half_open_success_threshold=1)

    Behavior:
      - CLOSED: normal operation; failures increment fail_count.
      - OPEN: immediately raise CircuitOpenError from before_call().
      - HALF_OPEN: allows `max_concurrent_half_open_probes` probes to check service; if a probe succeeds,
        we count it towards `half_open_success_threshold` and may close the circuit; if a probe fails, reopen.
    """
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_success_threshold: int = 1,
        max_concurrent_half_open_probes: int = 1,
    ):
        self.name = name
        self.failure_threshold = max(1, int(failure_threshold))
        self.recovery_timeout = float(recovery_timeout)
        self.half_open_success_threshold = max(1, int(half_open_success_threshold))
        self.max_concurrent_half_open_probes = max_concurrent_half_open_probes

        # state
        self._state = "CLOSED"  # CLOSED | OPEN | HALF_OPEN
        self._fail_count = 0
        self._opened_at: Optional[float] = None
        self._half_open_success_count = 0

        # concurrency control for probes and state transitions
        self._lock = asyncio.Lock()
        self._half_open_semaphore = asyncio.Semaphore(self.max_concurrent_half_open_probes)

    async def _maybe_transition(self):
        # called under lock before allowing calls
        if self._state == "OPEN" and self._opened_at is not None :
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                self._state == "HALF_OPEN"
                self._half_open_success_count = 0


    async def before_call(self):
        
        async with self._lock:
            await self._maybe_transition()
            if self._state == "OPEN":
                raise CircuitOpenError(f"circuit {self.name} is open")
            if self._state == "HALF_OPEN":
                if self._half_open_semaphore.locked() and self._half_open_semaphore._value <= 0:
                    # no more probes allowed; fail-fast
                    raise CircuitOpenError(f"circuit {self.name} is half-open and probes are saturated")
        # if closed or half-open and we have capacity, the caller proceeds

    async def _record_success(self):
        async with self._lock:
            if self._state in ("OPEN", "HALF_OPEN"):
                # a success in HALF_OPEN counts towards closing
                if self._state == "HALF_OPEN":
                    self._half_open_success_count += 1
                    if self._half_open_success_count >= self.half_open_success_threshold:
                        # close circuit
                        self._state = "CLOSED"
                        self._fail_count = 0
                        self._opened_at = None
                        self._half_open_success_count = 0
                else:
                    # success in OPEN shouldn't normally happen (we shouldn't be calling)
                    self._state = "CLOSED"
                    self._fail_count = 0
                    self._opened_at = None
            else:
                # CLOSED: reset fail_count on success
                self._fail_count = 0

    async def _record_failure(self):
        async with self._lock:
            if self._state == "HALF_OPEN":
                # any failure immediately re-opens
                self._state = "OPEN"
                self._opened_at = time.monotonic()
                self._fail_count = 0
                self._half_open_success_count = 0
            elif self._state == "CLOSED":
                self._fail_count += 1
                if self._fail_count >= self.failure_threshold:
                    self._state = "OPEN"
                    self._opened_at = time.monotonic()
                    self._fail_count = 0

    async def acquire_half_open_probe(self, timeout: Optional[float] = None) -> bool:
        """
        Acquire permission to run a probe when in HALF_OPEN. Returns True if acquired.
        """
        try:
            # semaphore acquire blocks asynchronously
            await asyncio.wait_for(self._half_open_semaphore.acquire(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def release_half_open_probe(self):
        try:
            self._half_open_semaphore.release()
        except ValueError:
            # don't crash
            pass


