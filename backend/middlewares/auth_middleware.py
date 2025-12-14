
from typing import Optional
from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from backend.common.retries import retry_transaction
from backend.user.dependencies import Authentication
from backend.user.repository import  identify_user_by_pid
from backend.middlewares.constants import logger


class AuthenticationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, session_maker,paths:str,maybe_auth_paths:Optional[str]):
        super().__init__(app)
        self.session_maker = session_maker
        self.paths = paths 

    async def dispatch(self, request: Request, call_next):
        
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
        session_pid=auth_token.get("session_pid")

        async def txn_fn():
            user_id=await identify_user_by_pid(self.session_maker,user_pid)
            return user_id

        user_identifier = await retry_transaction(txn_fn=txn_fn,async_session_maker=self.session_maker)
      
        if not user_identifier:
            logger.warning("auth.middleware.user_not_found", extra={
                "user_public_id": user_pid,
                "path": request.url.path
            })
            return JSONResponse(
                {"detail": "User unidentified and not authorized"},
                status_code=status.HTTP_403_FORBIDDEN,
            )
            
        request.state.user_identifier = user_identifier
        request.state.user_public_id = user_pid  # Store public_id for logging
        request.state.user_roles=user_roles
        request.state.role_version=role_version
        request.state.session_pid=session_pid

        logger.info("auth.middleware.success", extra={
            "user_public_id": user_pid,
            "path": request.url.path
        })

        response =  await call_next(request)

        return response