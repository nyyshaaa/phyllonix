
import asyncio
from asyncio import TimeoutError as AsyncioTimeoutError
import functools
import random
import socket
from typing import Any, Awaitable, Callable, Optional, Tuple, Type
from fastapi import HTTPException , status
from sqlalchemy.exc import DBAPIError,OperationalError,InterfaceError
from backend.common import logger
from backend.common.circuit_breaker import CircuitBreaker, CircuitOpenError

db_circuit = CircuitBreaker(name="postgres", failure_threshold=3, recovery_timeout=20.0, half_open_success_threshold=1, max_concurrent_half_open_probes=1)


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

def retry_read(
    *,
    attempts: int = 3,
    base_delay: float = 0.1,
    factor: float = 2.0,
    max_delay: float = 1.0,
    jitter: float = 0.15,
    is_retryable: Optional[Callable[[BaseException], bool]] = None,
    per_attempt_timeout: Optional[float] = None,
):
    """
    Decorator to retry a single async I/O call (reads, safe ops).
    - attempts: total attempts including first
    - per_attempt_timeout: optional per-attempt timeout (seconds)
    """
    if is_retryable is None:
        is_retryable = is_recoverable_exception

    def deco(fn: Callable[..., Awaitable[Any]]):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, attempts + 1):
                try:
                    if per_attempt_timeout:
                        return await asyncio.wait_for(fn(*args, **kwargs), timeout=per_attempt_timeout)
                    return await fn(*args, **kwargs)
                except asyncio.CancelledError:
                    # let cancellations propagate
                    raise
                except Exception as exc:
                    last_exc = exc
                    try:
                        retryable = is_retryable(exc)
                    except Exception:
                        retryable = False
                    if not retryable:
                        # not transient: re-raise
                        raise
                    if attempt == attempts:
                        # exhausted attempts
                        break
                    # backoff with jitter
                    delay = min(max_delay, base_delay * (factor ** (attempt - 1)))
                    # logger.debug("retryable_call: attempt %d failed, retrying in %f sec: %s", attempt, delay, exc)
                    await _sleep_with_jitter(delay, jitter)
                    continue
            # exhausted attempts: re-raise last exception preserving stack
            raise last_exc
        return wrapper
    return deco


async def retry_transaction(
    txn_fn: Callable[..., Awaitable[Any]],
    async_session_maker,
    *,
    attempts: int = 2,
    base_delay: float = 0.1,
    factor: float = 2.0,
    max_delay: float = 1.0,
    jitter: float = 0.15,
    if_retryable: Optional[Callable[[BaseException], bool]] = None,
    per_attempt_timeout: Optional[float] = None,
):
   
    if if_retryable is None:
        if_retryable = is_recoverable_exception

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
        
        async with async_session_maker() as session:
            try:
                if per_attempt_timeout:
                    result = await asyncio.wait_for(txn_fn(session), timeout=per_attempt_timeout)
                else:
                    result = await txn_fn(session)
                await session.commit()

                if acquired_probe:
                    db_circuit.release_half_open_probe()
                await db_circuit._record_success()

                return result
            
            except asyncio.CancelledError:
                await session.rollback()
                raise
            except Exception as exc:
                last_exc = exc
                await session.rollback()
                try:
                    retryable = if_retryable(exc)
                except Exception:
                    retryable = False
                if not retryable or attempt == attempts:
                    raise

                if acquired_probe:
                    db_circuit.release_half_open_probe()
                await db_circuit._record_failure()

                delay = min(max_delay, base_delay * (factor ** (attempt - 1)))
                logger.debug("transaction retry attempt %d failed; retrying in %f: %s", attempt, delay, exc)
                await _sleep_with_jitter(delay, jitter)
                continue

    raise last_exc






























