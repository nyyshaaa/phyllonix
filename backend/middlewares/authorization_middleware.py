from typing import Optional
from fastapi import Request, status
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from backend.schema.full_schema import Users
from backend.user.dependencies import Authentication
from backend.user.repository import check_user_roles_version, userid_by_public_id
from backend.common.logging_setup import get_logger

logger = get_logger("chlorophyll.auth.middleware")

# for endpoints which require roles verification for optimal security , roles are re-checked in refresh endpoint anyway while providing access tokens.
class AuthorizationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, session,paths:str,redis, role_cache_ttl: int = 30):
        super().__init__(app)
        self.session = session
        self.paths = paths 
        self.redis = redis
        self.role_cache_ttl = role_cache_ttl


    async def dispatch(self, request: Request, call_next):
        # Skip authorization for excluded paths
        if any(request.url.path.startswith(p) for p in self.paths):
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
        
        if not current_role_version:
            logger.warning("auth.authorization.user_not_found", extra={
                "path": request.url.path,
                "user_public_id": user_public_id
            })
            return JSONResponse(
                    {"detail": "No user found or access revoked"},   # should not happen as auth middleware passed
                    status_code=status.HTTP_401_UNAUTHORIZED
            )
        
        if int(current_role_version) != int(role_version):
            logger.warning("auth.authorization.role_version_mismatch", extra={
                "path": request.url.path,
                "token_role_version": role_version,
                "current_role_version": current_role_version,
                "user_public_id": user_public_id
            })
            return JSONResponse(
                {"detail": "Trigger re-login , role_version mismatch"},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        
        logger.debug("auth.authorization.success", extra={
            "path": request.url.path,
            "role_version": role_version
        })
        
        return await call_next(request)
    
