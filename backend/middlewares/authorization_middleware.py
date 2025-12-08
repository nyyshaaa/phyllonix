from typing import Optional
from fastapi import Request, status
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from backend.schema.full_schema import Users
from backend.user.dependencies import Authentication
from backend.user.repository import check_user_roles_version, userid_by_public_id
from backend.middlewares.constants import logger


# for endpoints which require roles verification for optimal security , roles are re-checked in refresh endpoint anyway while providing access tokens.
class AuthorizationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, session,paths:str, role_cache_ttl: int = 30):
        super().__init__(app)
        self.session = session
        self.paths = paths 
        self.role_cache_ttl = role_cache_ttl


    async def dispatch(self, request: Request, call_next):
        # Skip authorization for excluded paths
        if not any(request.url.path.startswith(p) for p in self.paths):
            return await call_next(request)
        
        identifier = getattr(request.state, "user_identifier", None)
        role_version = getattr(request.state, "role_version", None)
        user_public_id = getattr(request.state, "user_public_id", None)
        
        if not identifier:
            logger.warning("auth.authorization.missing_user", extra={
                "path": request.url.path
            })
            return JSONResponse(
                {"detail": "User not authenticated"},
                status_code=status.HTTP_401_UNAUTHORIZED
            )
        
        logger.debug("auth.authorization.check", extra={
            "path": request.url.path,
            "token_role_version": role_version
        })
        
        current_role_version = None
        async with self.session() as session:
            current_role_version=await check_user_roles_version(session,identifier,role_version)
        
        if current_role_version is None:
            logger.warning("auth.authorization.user_not_found", extra={
                "path": request.url.path,
                "user_public_id": user_public_id
            })
            return JSONResponse(
                    {"detail": "Role version mismatch, trigger re login"},  
                    status_code=status.HTTP_401_UNAUTHORIZED
            )
        
        
        logger.debug("auth.authorization.success", extra={
            "path": request.url.path,
            "role_version": role_version
        })
        
        return await call_next(request)
    
