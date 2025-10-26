

import base64
from datetime import datetime
import hashlib
import hmac
import json
import os
import time
from typing import Optional, Tuple

#** change this secret
CURSOR_SECRET = os.getenv("PHYL_CURSOR_SECRET", "dev-secret-change-me").encode()

def _sign(payload_bytes: bytes) -> str:
    sig = hmac.new(CURSOR_SECRET, payload_bytes, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")

#** chnage data types of cursor when cursor is chnaged
def decode_cursor(token: str, max_age: Optional[int] = None) -> Tuple[datetime, str]:
    try:
        token_part, sig_part = token.split(".")
    except ValueError:
        raise ValueError("Invalid cursor format")
    # restore padding and decode
    padded = token_part + "=" * ((4 - len(token_part) % 4) % 4)
    raw = base64.urlsafe_b64decode(padded)
    # verify sig
    expected = _sign(raw)
    if not hmac.compare_digest(expected, sig_part):
        raise ValueError("Cursor signature mismatch")
    payload = json.loads(raw.decode())
    if max_age is not None and int(time.time()) - payload.get("t", 0) > max_age:
        raise ValueError("Cursor expired")
    created_at_iso, id_value = payload["s"]
    return datetime.fromisoformat(created_at_iso), id_value

#** chnage data types of cursor when cursor is chnaged
def encode_cursor(last_cursor: datetime, last_cursor_id: str, ttl_seconds: int = 3600) -> str:
    payload = {
        "t": int(time.time()),
        "ttl": ttl_seconds,
        "s": [last_cursor.isoformat(), str(last_cursor_id)]
    }
    raw_bytes = json.dumps(payload, separators=(",", ":"), default=str).encode()
    bytes_encoded = base64.urlsafe_b64encode(raw_bytes).decode().rstrip("=")
    bytes_signed = _sign(raw_bytes)
    return f"{bytes_encoded}.{bytes_signed}"



def make_params_key(limit: int, cursor_token: Optional[str], q: Optional[str] = None, category: Optional[str] = None) -> str:
    # Keep suffix stable and deterministic. We include cursor token directly (it's opaque).
    # If cursor is a long token, you may hash it to keep key short
    parts = [f"limit={limit}"]
    parts.append(f"cursor={cursor_token or ''}")
    if q:
        parts.append(f"q={q}")
    if category:
        parts.append(f"cat={category}")
    joined = "|".join(parts)
    if len(joined) > 200:
        return hashlib.sha256(joined.encode()).hexdigest()
    return joined