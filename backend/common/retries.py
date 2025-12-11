
import asyncio
from asyncio import TimeoutError as AsyncioTimeoutError
import functools
import random
import socket
from typing import Any, Awaitable, Callable, Optional, Tuple, Type
from fastapi import HTTPException , status
from sqlalchemy.exc import DBAPIError,OperationalError,InterfaceError
from backend.common import logger



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
        async with async_session_maker() as session:
            try:
                if per_attempt_timeout:
                    result = await asyncio.wait_for(txn_fn(session), timeout=per_attempt_timeout)
                else:
                    result = await txn_fn(session)
                await session.commit()
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
        
                delay = min(max_delay, base_delay * (factor ** (attempt - 1)))
                logger.debug("transaction retry attempt %d failed; retrying in %f: %s", attempt, delay, exc)
                await _sleep_with_jitter(delay, jitter)
                continue

    raise last_exc































# ---------------------------------------------------------------------------------------------------------------------------------------------------------------

def _safe_name(obj) -> str:
    try:
        return type(obj).__name__
    except Exception:
        return ""


def is_recoverable_exception_old(exc: BaseException) -> bool:
    """
    Conservative retryable detection:
    - network/timeout errors
    - SQLAlchemy DBAPIError with connection_invalidated
    - asyncio.TimeoutError
    
    """

    # common python timeouts/connections
    if isinstance(exc, (AsyncioTimeoutError, TimeoutError, socket.timeout, ConnectionError, OSError)):
        return True

    if isinstance(exc, DBAPIError):
        # connection invalidated by engine
        if getattr(exc, "connection_invalidated", False):
            return True
        # underlying driver errors often in exc.orig - be conservative:
        orig = getattr(exc, "orig", None)
        if orig is not None:
           
            name = _safe_name(orig).lower()
            if any(k in name for k in ("timeout", "connection", "brokenpipe", "connectionrefused", "connectionreset","interfaceerror", "operationalerror")):
                return True
            
    if OperationalError and isinstance(exc, OperationalError):
        return True
    if InterfaceError and isinstance(exc, InterfaceError):
        return True

    return False


def retry_async_old(
    *,
    attempts: int = 1,
    base_delay: float = 0.2,
    factor: float = 2.0,
    max_delay: float = 10.0,
    jitter: float = 0.2,
    retry_on: Optional[Tuple[Type[BaseException], ...]] = None,
    if_retryable: Optional[Callable[[BaseException], bool]] = None,
):
    """
    Async exponential-backoff retry decorator with jitter.

    - attempts: total attempts including first.
    - if_retryable: optional function(exc) -> bool to decide based on exception (e.g. is_recoverable_exception)
    - retry_on: explicit exception classes to retry (if provided).
    """
    if retry_on is not None:
        retry_on = tuple(retry_on)

    def deco(fn: Callable):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, attempts + 1):
                print("retry here")
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    # check class
                    if retry_on is not None and not isinstance(exc, retry_on):
                        raise 
                    # check predicate
                    if if_retryable is not None and not if_retryable(exc):
                        raise
                    # compute delay
                    delay = min(max_delay, base_delay * (factor ** (attempt - 1)))
                    # jitter +/- jitter*delay
                    jitter_val = random.uniform(-jitter * delay, jitter * delay)
                    sleep_for = max(0.0, delay + jitter_val)
                    # metric example:
                    # RETRIES_TOTAL.labels(operation=fn.__name__).inc()
                    await asyncio.sleep(sleep_for)
            # if we exit loop, re-raise last:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,detail=f"{type(last_exc).__name__}")
        return wrapper
    return deco



