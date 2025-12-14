
import asyncio
from asyncio import TimeoutError as AsyncioTimeoutError
import functools
import random
import socket
from typing import Any, Awaitable, Callable, Optional, Tuple, Type
from fastapi import HTTPException , status
from sqlalchemy.exc import DBAPIError,OperationalError,InterfaceError
from backend.common import logger
from backend.common.circuit_breaker import CircuitOpenError
from backend.common.circuit_breaker import db_circuit

def is_recoverable_exception(exc: BaseException) -> bool:
    if isinstance(exc, asyncio.CancelledError):
        return False
    # common transient-ish exceptions
    if isinstance(exc, (TimeoutError, ConnectionError, OSError, OperationalError)):
        return True
    if isinstance(exc, DBAPIError):
        # SQLAlchemy's DBAPIError has connection_invalidated when connections dropped
        if getattr(exc, "connection_invalidated", False):
            return True
        orig = getattr(exc, "orig", None)
        if orig is not None:
            name = type(orig).__name__.lower()
            if any(k in name for k in ("timeout", "connection", "brokenpipe", "connectionrefused", "connectionreset")):
                return True
    return False

async def _sleep_with_jitter(delay: float, jitter: float) -> None:
    jitter_val = random.uniform(-jitter * delay, jitter * delay)
    await asyncio.sleep(max(0.0, delay + jitter_val))


async def retry_with_db_circuit(
    *,
    attempts: int = 3,
    base_delay: float = 0.1,
    factor: float = 2.0,
    max_delay: float = 1.0,
    jitter: float = 0.15,
    if_retryable: Optional[Callable[[BaseException], bool]] = None,
    per_attempt_timeout: Optional[float] = None,
    db_circuit = db_circuit
):
   
    if if_retryable is None:
        if_retryable = is_recoverable_exception

    
    def deco(fn: Callable):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, attempts + 1):
                
                try:
                    await db_circuit.before_call()
                except CircuitOpenError:
                    raise HTTPException(status_code=503, detail="service unavailable (db)")
                
                acquired_probe = False
                if db_circuit._state == "HALF_OPEN":
                    acquired_probe = await db_circuit.acquire_half_open_probe(timeout=0.1)
                    if not acquired_probe:
                        raise HTTPException(status_code=503, detail="service unavailable (db)")
                
               
                try:
                    if per_attempt_timeout:
                        result = await asyncio.wait_for(fn(*args,**kwargs), timeout=per_attempt_timeout)
                    else:
                        result = await fn(*args,**kwargs)

                    if acquired_probe:
                        db_circuit.release_half_open_probe()
                    await db_circuit._record_success()

                    return result
                
                except asyncio.CancelledError:
                    if acquired_probe:
                        db_circuit.release_half_open_probe()
                    raise
                except Exception as exc:
                    last_exc = exc

                    if acquired_probe:
                        db_circuit.release_half_open_probe()
                
                    try:
                        retryable = if_retryable(exc)
                    except Exception:
                        retryable = False
                    if not retryable or attempt == attempts:
                        raise

                    await db_circuit._record_failure()

                    delay = min(max_delay, base_delay * (factor ** (attempt - 1)))
                    logger.debug("transaction retry attempt %d failed; retrying in %f: %s", attempt, delay, exc)
                    await _sleep_with_jitter(delay, jitter)
                    continue

            raise last_exc
        return wrapper
    return deco






























