

import hashlib
import uuid
import msgpack
from typing import Any


def build_key(*parts: str) -> str:
    joined = ":".join(p for p in parts if p is not None and p != "")
    if len(joined) > 200:
        return hashlib.sha256(joined.encode()).hexdigest()
    return joined


def serialize(obj: Any) -> bytes:
    # msgpack is compact & fast; choose json if you prefer readability
    return msgpack.packb(obj, use_bin_type=True)

def deserialize(b: bytes) -> Any:
    return msgpack.unpackb(b, raw=False)


_RELEASE_LOCK_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
else
  return 0
end
"""

async def release_lock(redis_client, lock_key: str, token: str):
    try:
        await redis_client.eval(_RELEASE_LOCK_LUA, 1, lock_key, token)
    except Exception:
        # best-effort cleanup, failures are non-fatal
        try:
            await redis_client.delete(lock_key)
        except Exception:
            pass

