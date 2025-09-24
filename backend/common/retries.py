

import asyncio
from asyncio import TimeoutError as AsyncioTimeoutError
import functools
import random
from typing import Callable, Optional, Tuple, Type
from sqlalchemy.exc import DBAPIError


def is_transient_exception(exc: BaseException) -> bool:
    """
    Conservative transient detection:
    - network/timeout errors
    - SQLAlchemy DBAPIError with connection_invalidated
    - asyncio.TimeoutError
    
    """

    # common python timeouts/connections
    if isinstance(exc, (AsyncioTimeoutError, ConnectionError)):
        return True

    if isinstance(exc, DBAPIError):
        # connection invalidated by engine
        if getattr(exc, "connection_invalidated", False):
            return True
        # underlying driver errors often in exc.orig - be conservative:
        orig = getattr(exc, "orig", None)
        if orig is not None:
            name = type(orig).__name__
            if name.lower().startswith(("timeout", "connection", "interfaceerror", "operationalerror")):
                return True

    return False


def retry_async(
    *,
    attempts: int = 3,
    base_delay: float = 0.2,
    factor: float = 2.0,
    max_delay: float = 10.0,
    jitter: float = 0.2,
    retry_on: Optional[Tuple[Type[BaseException], ...]] = None,
    only_if: Optional[Callable[[BaseException], bool]] = None,
):
    """
    Async exponential-backoff retry decorator with jitter.

    - attempts: total attempts including first.
    - only_if: optional function(exc) -> bool to decide based on exception (e.g. is_transient_exception)
    - retry_on: explicit exception classes to retry (if provided).
    """
    retry_on = tuple(retry_on) if retry_on else None

    def deco(fn: Callable):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    # check class
                    if not isinstance(exc, retry_on):
                        raise
                    # check predicate
                    if only_if is not None and not only_if(exc):
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
            raise last_exc
        return wrapper
    return deco