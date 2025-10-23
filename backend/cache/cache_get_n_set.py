


import asyncio
from typing import Any, Callable, Optional
from backend.cache._cache import REDIS_LOCK_TIMEOUT, redis_client
from backend.cache.utils import build_key, deserialize, serialize

CATALOG_VERSION_KEY = "phyl:catalog:version"


async def get_bytes(key: str) -> Optional[bytes]:
    return await redis_client.get(key)

async def set_bytes(key: str, data: bytes, ttl_seconds: int):
    await redis_client.set(key, data, ex=ttl_seconds)

async def bump_catalog_version():
    await redis_client.incr(CATALOG_VERSION_KEY)


async def cache_get_or_set(
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
    version = await redis_client.get(CATALOG_VERSION_KEY)
    if version is None:
        # initialize version to 1 if missing
        await redis_client.set(CATALOG_VERSION_KEY, "1")
        version = "1"
    version_str = version.decode() if isinstance(version, (bytes, bytearray)) else str(version)
    key = build_key("phyl", namespace, f"v{version_str}", key_suffix)
    raw = await get_bytes(key)
    if raw is not None:
        # we have a cached value
        # if mode == "stale":
        #     ttl_remaining = await redis_client.ttl(key)  # -2 if missing, -1 if no ttl
        #     try:
        #         value = deserialize(raw)
        #     except Exception:
        #         # corrupted entry -> remove and treat as miss
        #         await redis_client.delete(key)
        #         raw = None
        #         value = None
        #     if raw is not None:
        #         # if nearing expiry, attempt to refresh in background
        #         if ttl_remaining is not None and isinstance(ttl_remaining, int) and ttl_remaining >= 0 and ttl_remaining <= stale_window:
        #             got = await redis_client.set(lock_key, "1", nx=True, ex=lock_timeout)
        #             if got:
        #                 # spawn background refresh
        #                 async def _bg_refresh():
        #                     try:
        #                         new_val = await loader()
        #                         await redis_client.set(key, _serialize(new_val), ex=ttl)
        #                     finally:
        #                         await redis_client.delete(lock_key)
        #                 asyncio.create_task(_bg_refresh())
        #         return value
        # mode == "wait" or stale refresh not required
        try:
            print("deserializing cache hit")
            return deserialize(raw)
        except Exception:
            await redis_client.delete(key)
            raw = None

    print("cache miss")
    # cache miss => try lock
    lock_key = key + ":lock"
    locked = await redis_client.set(lock_key, "1", nx=True, ex=REDIS_LOCK_TIMEOUT)
    if locked:
        try:
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
            await redis_client.delete(lock_key)
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
        # else:
        #     # mode == "stale": short wait then fallback to compute
        #     await asyncio.sleep(0.15)
        #     raw_after = await redis_client.get(key)
        #     if raw_after is not None:
        #         try:
        #             return deserialize(raw_after)
        #         except Exception:
        #             await redis_client.delete(key)
        #     # fallback to compute (do NOT take lock here to avoid heavy thundering)
        #     val = await loader()
        #     try:
        #         await redis_client.set(key, serialize(val), ex=ttl)
        #     except Exception:
        #         pass
        #     return val