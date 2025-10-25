


import asyncio
from typing import Any, Callable, Optional
import uuid
from backend.cache._cache import REDIS_LOCK_TIMEOUT, redis_client
from backend.cache.utils import build_key, deserialize, release_lock, serialize

CATALOG_VERSION_KEY = "phyl:catalog:version"


async def get_bytes(key: str) -> Optional[bytes]:
    return await redis_client.get(key)

async def set_bytes(key: str, data: bytes, ttl_seconds: int):
    await redis_client.set(key, data, ex=ttl_seconds)

async def bump_catalog_version():
    await redis_client.incr(CATALOG_VERSION_KEY)


async def cache_get_or_set_product_listings(
    namespace: str,
    key_suffix: str,
    ttl: int,
    loader: Callable[[], Any],
    mode: str = "wait",
    stale_window: int = 15,  # seconds before expiry to refresh in background
    lock_timeout: int = 8,
    # serializer: Callable[[Any], bytes] = lambda x: msgpack.packb(x, use_bin_type=True),
    # deserializer: Callable[[bytes], Any] = lambda b: msgpack.unpackb(b, raw=False),
    # lock_timeout: int = 10,
) -> Any:
    """
    mode="stale": if cached value exists we return it immediately; if TTL <= stale_window, try to refresh in BG.
    mode="wait": if cache missing, wait for the builder to complete (poll) and return result (blocking).
    loader: zero-arg async callable closure that returns the fresh value to cache.
    """
    # include catalog version in namespace/key to enable global invalidation
    # version = await redis_client.get(CATALOG_VERSION_KEY)
    # if version is None:
    #     # initialize version to 1 if missing
    #     await redis_client.set(CATALOG_VERSION_KEY, "1")
    #     version = "1"
    # version_str = version.decode() if isinstance(version, (bytes, bytearray)) else str(version)
    key = build_key("phyl", namespace, key_suffix)
    raw = await get_bytes(key)
    if raw is not None:
        # we have a cached value
        #** may add background refresh when ttl is nearing expiry for stale modes
        try:
            print("deserializing cache hit")
            return deserialize(raw)
        except Exception:
            await redis_client.delete(key)
            raw = None

    print("cache miss")

    # cache miss => try lock
    lock_key = key + ":lock"
    token = uuid.uuid4().hex
    locked = await redis_client.set(lock_key, token, nx=True, ex=REDIS_LOCK_TIMEOUT)
    if locked:
        try:
            # re-check cache: another process may have populated while we raced for lock 
            # as in like someone acquired lock and released it as well , so in case we try to acquire lock after that .
            raw_after = await get_bytes(key)
            if raw_after is not None:
                try:
                    return deserialize(raw_after)
                except Exception:
                    await redis_client.delete(key)
                
            value = await loader()
            print("lock loading from db")
            try:
                await set_bytes(key, serialize(value), ttl)
            except Exception as e:
                print("set fails", e)
                # if set fails, still return value
                pass
            return value
        finally:
            await release_lock(redis_client, lock_key, token)
    else:
        # someone else is computing 
        if mode == "wait":
            # poll until cache appears or timeout
            waited = 0.0
            interval = 0.05
            timeout = lock_timeout + 1
            while waited < timeout:
                await asyncio.sleep(interval)
                waited += interval
                raw_after = await redis_client.get(key)
                if raw_after is not None:
                    try:
                        return deserialize(raw_after)
                    except Exception:
                        await redis_client.delete(key)
                        break
            # fallback to compute ourselves
            val = await loader()
            try:
                await redis_client.set(key, serialize(val), ex=ttl)
            except Exception:
                pass
            return val
        else:
            # mode == "stale": short wait then fallback to compute
            await asyncio.sleep(0.15)
            raw_after = await redis_client.get(key)
            if raw_after is not None:
                try:
                    return deserialize(raw_after)
                except Exception:
                    await redis_client.delete(key)
            # fallback to compute (do NOT take lock here to avoid heavy thundering)
            val = await loader()
            try:
                await redis_client.set(key, serialize(val), ex=ttl)
            except Exception:
                pass
            return val