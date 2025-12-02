
from typing import Optional
from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from backend.user.dependencies import Authentication
from backend.user.repository import  identify_user_by_pid
from backend.middlewares.constants import logger


class AuthenticationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, session,paths:str,maybe_auth_paths:Optional[str]):
        super().__init__(app)
        self.session = session
        self.paths = paths 

    async def dispatch(self, request: Request, call_next):
        # Skip authentication for excluded paths
        if any(request.url.path.startswith(p) for p in self.paths):
            return await call_next(request)
        
        logger.info("auth.middleware.attempt", extra={
            "path": request.url.path,
            "method": request.method
        })
        
        try:
            auth_token = await Authentication()(request) 
        except Exception as e:
            detail = getattr(e, "detail", "Missing or Invalid Auth Headers")
            logger.warning("auth.middleware.failed", extra={
                "reason": detail,
                "path": request.url.path,
                "method": request.method
            })
            return JSONResponse(
                    {"detail": detail or "Missing or Invalid Auth Headers"},
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )
        
        user_pid = auth_token.get("sub")
        user_roles=auth_token.get("roles")
        role_version=auth_token.get("role_version")

        # device_session_plain = request.cookies.get("session_token") or request.headers.get("X-Device-Token") or None


        async with self.session() as session:

            user_id=await identify_user_by_pid(session,user_pid)

            user_identifier=user_id
            if not user_identifier:
                logger.warning("auth.middleware.user_not_found", extra={
                    "user_public_id": user_pid,
                    "path": request.url.path
                })
                return JSONResponse(
                    {"detail": "User unidentified and not authorized"},
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            
            # Attach the identifier to the request state to use in other middlewares
            request.state.user_identifier = user_identifier
            request.state.user_public_id = user_pid  # Store public_id for logging
            request.state.user_roles=user_roles
            request.state.role_version=role_version

        logger.info("auth.middleware.success", extra={
            "user_public_id": user_pid,
            "path": request.url.path
        })

        response =  await call_next(request)

        return response