from typing import Optional
from fastapi import Request, status
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from backend.schema.full_schema import Users
from backend.user.dependencies import Authentication
from backend.user.repository import check_user_roles, userid_by_public_id


class AuthenticationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, session,paths:str):
        super().__init__(app)
        self.session = session
        self.paths = paths 

    async def dispatch(self, request: Request, call_next):
        if any(request.url.path.startswith(p) for p in self.paths):
            # Skip authentication for paths that don't require it
            return await call_next(request)
        

        
        identifier = request.state.user_identifier
        role_version = request.state.role_version

        async with self.session() as session:
            user_id=await check_user_roles(session,identifier,role_version)
        
        if not user_id:
            return JSONResponse(
                    {"detail": "Trigger access refresh , role_version mismatch"},
                    status_code=status.HTTP_401_UNAUTHORIZED
            )
        
        return await call_next(request)
    
