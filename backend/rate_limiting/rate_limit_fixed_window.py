
import time
from typing import Optional
from fastapi import HTTPException, Request , status
from backend.rate_limiting.constants import DEFAULT_LIMIT, DEFAULT_WINDOW, FAIL_OPEN, RATE_LIMIT_PREFIX, REDIS_TIMEOUT_SECONDS, USE_IN_MEMORY_FALLBACK
from backend.cache._cache import redis_client
from backend.rate_limiting.utils import LUA_FIXED_WINDOW_INCR_AND_PEXPIRE, _ensure_lua_loaded, _identifier_from_request
from backend.rate_limiting.constants import _in_memory_counters,_in_memory_lock


async def allow_request(request: Request, limit: int, window: int, route_key: Optional[str] = None):
    if route_key is None:
        route_key = request.url.path
    identifier, scope = _identifier_from_request(request)
    key = f"{RATE_LIMIT_PREFIX}:{scope}:{identifier}:{route_key}"
    allowed, remaining, reset = await redis_allow(key, limit, window)
   
    request.state.rate_limit = {"limit": limit, "remaining": remaining, "reset": reset}
    if not allowed:
        retry_after = max(0, reset - int(time.time()))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
            headers={"Retry-After": str(retry_after)}
        )
    return True
    
async def redis_allow(key: str, limit: int, window: int):
    """
    Returns (allowed: bool, remaining: int, reset_ts: int)
    """
    rc = redis_client
    pexpire_ms = int(window * 1000)
    sha = await _ensure_lua_loaded()

    try:
        if sha:
            res = await rc.evalsha(sha, 1, key, pexpire_ms, timeout=REDIS_TIMEOUT_SECONDS)
        else:
            res = await rc.eval(LUA_FIXED_WINDOW_INCR_AND_PEXPIRE, 1, key, pexpire_ms, timeout=REDIS_TIMEOUT_SECONDS)
       
        if not res or len(res) < 2 :
            # conservative fallback: allow
            now = int(time.time())
            return True, max(0, limit - 1), now + window
        count = int(res[0])
        ttl_ms = int(res[1])
        now = int(time.time())
        reset_ts = now + (ttl_ms // 1000) if ttl_ms > 0 else now + window
        allowed = count <= limit
        remaining = max(0, limit - count) if allowed else 0
        return allowed, remaining, reset_ts
    except Exception as e:

        # Redis operation failed (timeout, network, auth)
        if USE_IN_MEMORY_FALLBACK:
            try:
                return await _in_memory_allow(key, limit, window)
            except Exception:
                pass
        # if fallback not usable, obey FAIL_OPEN policy
        if FAIL_OPEN:
            now = int(time.time())
            return True, max(0, limit - 1), now + window
        else:
            # fail-closed: deny
            now = int(time.time())
            return False, 0, now + window


# simple non disributed fallaback for redis unavailability , use only for short outages 
async def _in_memory_allow(key: str, limit: int, window: int):
    """
    Simple per-process fixed-window counter fallback.
    use only for short outages .
    """
    async with _in_memory_lock:
        now = int(time.time())
        existing = _in_memory_counters.get(key)
        if not existing or existing["expires_at"] <= now:
            _in_memory_counters[key] = {"count": 1, "expires_at": now + window}
            remaining = max(0, limit - 1)
            reset_ts = now + window
            return True, remaining, reset_ts
        else:
            if existing["count"] >= limit:
                remaining = 0
                reset_ts = existing["expires_at"]
                return False, remaining, reset_ts
            else:
                existing["count"] += 1
                remaining = max(0, limit - existing["count"])
                reset_ts = existing["expires_at"]
                return True, remaining, reset_ts

def rate_limit_dependency(limit: int = DEFAULT_LIMIT, window: int = DEFAULT_WINDOW, route_key: Optional[str] = None):
    """
    Use as: Depends(rate_limit_dependency(limit=10, window=60, route_key="login"))
    Returns a dependency coroutine that inspects Request and enforces the limit.
    """
    async def _dep(request: Request):
        await allow_request(request, limit, window, route_key)
    return _dep




