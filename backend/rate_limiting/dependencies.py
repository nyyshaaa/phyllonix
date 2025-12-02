
import time
from typing import Optional
from fastapi import HTTPException, Request,status
from backend.rate_limiting.constants import RATE_LIMIT_PREFIX
from backend.rate_limiting.rate_limit_fixed_window import redis_allow
from backend.rate_limiting.rate_limit_sliding_window import redis_allow_sliding
from backend.rate_limiting.utils import _identifier_from_request


def rate_limit_dependency(limit=10, window=60, route_key: Optional[str] = None, rate_lim_style="fixed"):
    async def _dep(request: Request):
        if route_key is None:
            route_key = request.url.path
        identifier, scope = _identifier_from_request(request)
        key = f"{RATE_LIMIT_PREFIX}:{scope}:{identifier}:{route_key}"
        if rate_lim_style == "sliding":
            allowed, remaining, reset = await redis_allow_sliding(key, limit, window)
        elif rate_lim_style == "fixed":
            allowed, remaining, reset = await redis_allow(key, limit, window)
        request.state.rate_limit = {"limit": limit, "remaining": remaining, "reset": reset}
        if not allowed:
            retry_after = max(0, reset - int(time.time()))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests",
                headers={"Retry-After": str(retry_after)}
        )
    return _dep
