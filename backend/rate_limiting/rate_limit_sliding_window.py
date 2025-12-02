
import math
import time
import uuid
from backend.rate_limiting.constants import FAIL_OPEN, USE_IN_MEMORY_FALLBACK
from backend.cache._cache import redis_client
from backend.rate_limiting.lua_scripts import LUA_SLIDING_WINDOW
from backend.rate_limiting.utils import _ensure_lua_loaded, _in_memory_allow


async def redis_allow_sliding(key: str, limit: int, window_seconds: int):
    """
    Sliding window: returns (allowed: bool, remaining: int, reset_ts: int)
    """
    rc = redis_client
    window_ms = int(window_seconds * 1000)
    now_ms = int(time.time() * 1000)
    # unique member for zadd: use timestamp + random UUID fragment
    member = f"{now_ms}-{uuid.uuid4().hex[:8]}"

    sha = await _ensure_lua_loaded()
    try:
        if sha:
            res = await rc.evalsha(sha, 1, key, window_ms, limit, now_ms, member)
        else:
            res = await rc.eval(LUA_SLIDING_WINDOW, 1, key, window_ms, limit, now_ms, member)
      
        if not res or len(res) < 3:
            # conservative fallback: allow
            allowed = True
            remaining = max(0, limit - 1)
            reset_ts = int(time.time()) + window_seconds
            return allowed, remaining, reset_ts
        cur_count = int(res[0])
        reset_ms = int(res[1])
        allowed_flag = int(res[2])  # 1 or 0
        allowed = allowed_flag == 1
        remaining = max(0, limit - cur_count) if allowed else 0
        # reset timestamp in unix seconds
        retry_after_secs = math.ceil(reset_ms / 1000.0) if reset_ms >= 0 else window_seconds
        reset_ts = int(time.time()) + retry_after_secs
        return allowed, remaining, reset_ts
    except Exception:
        # fallback: use in-memory or fail-open policy
        if USE_IN_MEMORY_FALLBACK:
            return await _in_memory_allow(key, limit, window_seconds)
        if FAIL_OPEN:
            now = int(time.time())
            return True, max(0, limit - 1), now + window_seconds
        else:
            now = int(time.time())
            return False, 0, now + window_seconds