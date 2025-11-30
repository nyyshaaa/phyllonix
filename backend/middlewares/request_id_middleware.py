# request_id_middleware.py
import uuid
from fastapi.responses import JSONResponse,status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from backend.common.logging_setup import request_id_ctx

class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
      
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        token = request_id_ctx.set(req_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id

        request_id_ctx.reset(token)

        return response
