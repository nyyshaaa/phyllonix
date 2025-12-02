


LUA_SLIDING_WINDOW = """
local key = KEYS[1]
local window_ms = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local now_ms = tonumber(ARGV[3])
local member = ARGV[4]

-- remove old entries (score <= now_ms - window_ms)
oldest_timestamp = now_ms - window_ms
redis.call("ZREMRANGEBYSCORE", key, 0, min_score)

-- current number of events in window
local current = redis.call("ZCARD", key)

local allowed = 0
if tonumber(current) < limit then
  -- add current event
  redis.call("ZADD", key, now_ms, member)
  -- ensure key expires after window_ms (so idle keys are removed)
  redis.call("PEXPIRE", key, window_ms)
  current = current + 1
  allowed = 1
end

-- compute reset: time until earliest event + window_ms - now_ms
local reset_ms = window_ms
local oldest = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")
if oldest and #oldest >= 2 then
  local oldest_score = tonumber(oldest[2])
  reset_ms = (oldest_score + window_ms) - now_ms
  if reset_ms < 0 then reset_ms = 0 end
else
  reset_ms = window_ms
end

return {current, reset_ms, allowed}
"""


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