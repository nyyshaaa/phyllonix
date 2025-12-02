
from time import time
from fastapi import Request
from backend.rate_limiting.constants import _redis_lock,_in_memory_counters,_in_memory_lock
from backend.cache._cache import redis_client

# A small Lua script: INCR the key, and if newly created, set expiry atomically.
# Returns [counter, ttl_seconds]
LUA_FIXED_WINDOW_INCR_AND_PEXPIRE = """
local counter
counter = redis.call("INCR", KEYS[1])
if tonumber(counter) == 1 then
  redis.call("PEXPIRE", KEYS[1], ARGV[1])
else
  -- ensure TTL exists, return TTL in ms
  local ttl = redis.call("PTTL", KEYS[1])
  if ttl < 0 then
    redis.call("PEXPIRE", KEYS[1], ARGV[1])
  end
end
local ttl = redis.call("PTTL", KEYS[1])
return {counter, ttl}
"""

async def _ensure_lua_loaded():
    """
    Load the Lua script into Redis script cache and store SHA.
    Called once lazily.
    """
   
    if _script_sha:
        return _script_sha
    async with _redis_lock:
        if _script_sha:
            return _script_sha
        rc=redis_client
        try:
            _script_sha = await rc.script_load(LUA_FIXED_WINDOW_INCR_AND_PEXPIRE)
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

