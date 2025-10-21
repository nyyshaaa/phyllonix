

import base64
from datetime import datetime, time
import hashlib
import hmac
import json
import os
from typing import Optional, Tuple

CURSOR_SECRET = os.getenv("PHYL_CURSOR_SECRET", "dev-secret-change-me").encode()

def _sign(payload_bytes: bytes) -> str:
    sig = hmac.new(CURSOR_SECRET, payload_bytes, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")


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


def encode_cursor(created_at: datetime, id_value: str, ttl_seconds: int = 3600) -> str:
    payload = {
        "t": int(time.time()),
        "ttl": ttl_seconds,
        "s": [created_at.isoformat(), str(id_value)]
    }
    raw = json.dumps(payload, separators=(",", ":"), default=str).encode()
    token = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    sig = _sign(raw)
    return f"{token}.{sig}"