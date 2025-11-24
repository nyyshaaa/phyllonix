from typing import Optional
from fastapi import Request, status
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from backend.schema.full_schema import Users
from backend.user.dependencies import Authentication
from backend.user.repository import check_user_roles_version, userid_by_public_id

# for endpoints which require roles verification for optimal security , roles are re-checked in refresh endpoint anyway while providing access tokens.
class AuthorizationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, session,paths:str,redis, role_cache_ttl: int = 30):
        super().__init__(app)
        self.session = session
        self.paths = paths 
        self.redis = redis
        self.role_cache_ttl = role_cache_ttl


    async def dispatch(self, request: Request, call_next):
        if any(request.url.path.startswith(p) for p in self.paths):
            return await call_next(request)
        
        identifier = request.state.user_identifier
        role_version = request.state.role_version
        
        current_role_version = None
        async with self.session() as session:
            current_role_version=await check_user_roles_version(session,identifier,role_version)
        
        if not current_role_version:
            return JSONResponse(
                    {"detail": "No user found or access revoked"},   # should not happen as auth middleware passed
                    status_code=status.HTTP_401_UNAUTHORIZED
            )
        
        if int(current_role_version) != int(role_version):
            return JSONResponse(
                {"detail": "Trigger re-login , role_version mismatch"},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        
        return await call_next(request)
    
