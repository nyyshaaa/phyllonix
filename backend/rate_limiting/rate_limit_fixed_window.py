
import time
from typing import Optional
from fastapi import HTTPException, Request , status
from backend.rate_limiting.constants import DEFAULT_LIMIT, DEFAULT_WINDOW, FAIL_OPEN, RATE_LIMIT_PREFIX, REDIS_TIMEOUT_SECONDS, USE_IN_MEMORY_FALLBACK
from backend.cache._cache import redis_client
from backend.rate_limiting.utils import LUA_FIXED_WINDOW_INCR_AND_PEXPIRE, LUA_SLIDING_WINDOW, _ensure_lua_loaded, _identifier_from_request, _in_memory_allow
from backend.rate_limiting.constants import _in_memory_counters,_in_memory_lock

    
async def redis_allow(key: str, limit: int, window: int ):
    """
    Returns (allowed: bool, remaining: int, reset_ts: int)
    """
    rc = redis_client
    pexpire_ms = int(window * 1000)
    sha = await _ensure_lua_loaded("fixed_window")

    print("Using Fixed Window Rate Limiting Strategy")

    try:
        if sha:
            res = await rc.evalsha(sha, 1, key, pexpire_ms)
        else:
            res = await rc.eval(LUA_FIXED_WINDOW_INCR_AND_PEXPIRE, 1, key, pexpire_ms)
       
        if not res or len(res) < 2 :
            # conservative fallback: allow
            now = int(time.time())
            return True, max(0, limit - 1), now + window
        count = int(res[0])
        ttl_ms = int(res[1])
        print("Fixed Window Rate Limiting - count:",count," ttl_ms:",ttl_ms)
         # reset timestamp in unix seconds
        now = int(time.time())
        reset_ts = now + (ttl_ms // 1000) if ttl_ms > 0 else now + window
        allowed = count <= limit
        remaining = max(0, limit - count) if allowed else 0
        return allowed, remaining, reset_ts
    except Exception as e:
        print("Redis rate limiting error:", str(e))

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












