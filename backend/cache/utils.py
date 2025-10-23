

import hashlib
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