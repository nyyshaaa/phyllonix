
import time
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from backend.rate_limiting.constants import DEFAULT_LIMIT, DEFAULT_WINDOW, RATE_LIMIT_PREFIX
from backend.rate_limiting.rate_limit_fixed_window import redis_allow
from backend.rate_limiting.rate_limit_sliding_window import redis_allow_sliding
from backend.rate_limiting.utils import _identifier_from_request
from backend.middlewares.constants import logger



class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limit: int = DEFAULT_LIMIT, window: int = DEFAULT_WINDOW):
        super().__init__(app)
        self.limit = limit
        self.window = window

    async def dispatch(self, request: Request, call_next):

        # If a per-route dependency already set request.state.rate_limit, proceed through the request.
        if getattr(request.state, "rate_limit", None):
            response = await call_next(request)
            rl = request.state.rate_limit
            response.headers["X-RateLimit-Limit"] = str(rl["limit"])
            response.headers["X-RateLimit-Remaining"] = str(rl["remaining"])
            response.headers["X-RateLimit-Reset"] = str(rl["reset"])
            return response
        
        # per-app override set on app.state for defaults
        cfg = getattr(request.app, "state", None)
        rl_cfg = getattr(request.app.state, "rate_limit", None) if cfg else None
        limit = rl_cfg.get("limit", self.limit) if rl_cfg else self.limit
        window = rl_cfg.get("window", self.window) if rl_cfg else self.window

        rate_limit_strategy = getattr(request.app.state, "rate_limit_strategy", "fixed_window")


      
        identifier, scope = _identifier_from_request(request)
        route_key = request.url.path
        key = f"{RATE_LIMIT_PREFIX}:{scope}:{identifier}:{route_key}"
        if rate_limit_strategy == "sliding_window":
            try:
                allowed, remaining, reset = await redis_allow_sliding(key, limit, window)
            except Exception as e:
                return await call_next(request)

        if rate_limit_strategy == "fixed_window":
            try:
                allowed, remaining, reset = await redis_allow(key, limit, window)
            except Exception as e:
                return await call_next(request)
        request.state.rate_limit = {"limit": limit, "remaining": remaining, "reset": reset}
        if not allowed:
            print("not allowed rate limit reached")
            retry_after = max(0, reset - int(time.time()))
            return Response(status_code=status.HTTP_429_TOO_MANY_REQUESTS, content="Too many requests", headers={"Retry-After": str(retry_after)})
        response = await call_next(request)
        rl = request.state.rate_limit
        response.headers["X-RateLimit-Limit"] = str(rl["limit"])
        response.headers["X-RateLimit-Remaining"] = str(rl["remaining"])
        response.headers["X-RateLimit-Reset"] = str(rl["reset"])
        return response
        
