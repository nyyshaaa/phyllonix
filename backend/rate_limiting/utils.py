
from time import time
from fastapi import Request
from backend.rate_limiting.constants import _asyncio_lock,_in_memory_counters,_in_memory_lock
from backend.cache._cache import redis_client

from backend.rate_limiting.lua_scripts import LUA_FIXED_WINDOW_INCR_AND_PEXPIRE, LUA_SLIDING_WINDOW

WHICH_RATE_LIMITING_STRATEGY = LUA_SLIDING_WINDOW


async def _ensure_lua_loaded():
    """
    Load the Lua script into Redis script cache and store SHA.
    Called once lazily.
    """
   
    if _script_sha:
        return _script_sha
    async with _asyncio_lock:
        if _script_sha:
            return _script_sha
        rc=redis_client
        try:
            _script_sha = await rc.script_load(WHICH_RATE_LIMITING_STRATEGY)
            return _script_sha
        except Exception:
            # If script_load fails, we'll fallback to EVAL (slower) in calls
            _script_sha = None
            return None
        
def _identifier_from_request(request: Request):
    """
    authenticated user_id or fallback to ip 
    """
    user_identifier = getattr(request.state, "user_identifier", None)
    if user_identifier:
        return str(user_identifier), "user"
    # X-Forwarded-For: trust only when behind proper proxy; adapt as needed
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        client_host = xff.split(",")[0].strip()
    else:
        client_host = request.client.host if request.client else "unknown"
    return client_host or "unknown", "ip"

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



