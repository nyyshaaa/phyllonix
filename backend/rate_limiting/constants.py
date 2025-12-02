
import asyncio
from typing import Optional


DEFAULT_LIMIT = 20         # default requests
DEFAULT_WINDOW = 60         # seconds
RATE_LIMIT_PREFIX = "rl"    # redis key prefix
REDIS_TIMEOUT_SECONDS = 0.5
FAIL_OPEN = True                  # if redis is unavailable, allow requests (True) or deny (False)
USE_IN_MEMORY_FALLBACK = True     # allow simple local fallback when redis fails (not distributed)

_script_sha: Optional[str] = None
_redis_lock = asyncio.Lock()


_in_memory_counters = {}
_in_memory_lock = asyncio.Lock()