import asyncio
import time
import uuid
from backend.cache._cache import redis_client
from backend.cache.utils import deserialize, release_lock, serialize

PRODUCT_DETAIL_TTL = 15 * 60  # 15 min
REDIS_LOCK_TIMEOUT = 5  # seconds

async def cache_get_n_set_product_details(session, product_public_id: str,get_product_details_db):
    key = f"product:{product_public_id}"
    lock_key = key + ":lock"

    # Try to get from cache
    raw = await redis_client.get(key)
    if raw:
        try:
            return deserialize(raw)
        except Exception:
            await redis_client.delete(key)

    # Acquire lock for dogpile protection
    token = uuid.uuid4().hex
    locked = await redis_client.set(lock_key, token, nx=True, ex=REDIS_LOCK_TIMEOUT)

    if locked:
        try:
            # Re-check cache after acquiring lock
            raw_after = await redis_client.get(key)
            if raw_after:
                try:
                    return deserialize(raw)
                except Exception:
                    await redis_client.delete(key)

            # Fetch from DB
            product_details = await get_product_details_db(session, product_public_id)
            updated_at = product_details.get("updated_at")
           
            updated_at_ts = int(updated_at.timestamp())

            product_details["_cached_at"] = updated_at_ts

            # Store in cache
            await set_product_cache_if_newer(redis_client, product_public_id, product_details, 
                                             updated_at_ts, PRODUCT_DETAIL_TTL)
            return product_details
            
        finally:
            await release_lock(redis_client, lock_key, token)
    else:
        # Someone else is fetching — wait briefly and retry
        waited = 0.0
        interval = 0.05
        timeout = REDIS_LOCK_TIMEOUT + 1
        while waited < timeout:
            await asyncio.sleep(interval)
            waited += interval
            raw_after = await redis_client.get(key)
            if raw_after:
                try:
                    return deserialize(raw_after)
                except Exception:
                    await redis_client.delete(key)
                    break
        # Fallback: fetch ourselves if cache still empty
        product_details = await get_product_details_db(session, product_public_id)
        updated_at = product_details.get("updated_at")
           
        updated_at_ts = int(updated_at.timestamp())
        product_details["_cached_at"] = updated_at_ts

        # Store in cache
        await set_product_cache_if_newer(redis_client, product_public_id, product_details, 
                                            updated_at_ts, PRODUCT_DETAIL_TTL)
        return product_details
    


async def set_product_cache_if_newer(redis_client, public_id: str, payload: dict, new_ts: int, ttl: int):
    """
    Atomically set product cache only if new_ts >= existing version.
    payload must be serializable (dict). new_ts is int (epoch seconds).
    """
    value_key = f"product:{public_id}"
    ver_key = value_key + ":ver"
    data = serialize(payload)
    try:
        res = await redis_client.eval(_SET_IF_NEWER_LUA, 2, value_key, ver_key, data, str(new_ts), str(ttl))
        return bool(res)
    except Exception:
        pass
        return False
        

_SET_IF_NEWER_LUA = """
local cur = redis.call("GET", KEYS[2])
if not cur then cur = "0" end
local newv = tonumber(ARGV[2])
local curv = tonumber(cur)
if newv >= curv then
  redis.call("SET", KEYS[1], ARGV[1], "EX", ARGV[3])
  redis.call("SET", KEYS[2], ARGV[2], "EX", ARGV[3])
  return 1
else
  return 0
end
"""