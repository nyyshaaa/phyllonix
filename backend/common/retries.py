
import asyncio
from asyncio import TimeoutError as AsyncioTimeoutError
import functools
import random
import socket
from typing import Callable, Optional, Tuple, Type
from fastapi import HTTPException , status
from sqlalchemy.exc import DBAPIError,OperationalError,InterfaceError

def _safe_name(obj) -> str:
    try:
        return type(obj).__name__
    except Exception:
        return ""


def is_recoverable_exception(exc: BaseException) -> bool:
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


def retry_async(
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