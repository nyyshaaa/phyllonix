
from typing import Optional
from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from backend.user.dependencies import Authentication
from backend.user.repository import  identify_user_by_pid


class AuthenticationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, session,paths:str,maybe_auth_paths:Optional[str]):
        super().__init__(app)
        self.session = session
        self.paths = paths 

    async def dispatch(self, request: Request, call_next):
        print("Auth Middleware called for path:", request.url.path)
        if any(request.url.path.startswith(p) for p in self.paths):
            return await call_next(request)
        
        try:
            auth_token = await Authentication()(request) 
        except Exception as e:
            return JSONResponse(
                    {"detail": e.detail or "Missing or Invalid Auth Headers"},
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
                return JSONResponse(
                    {"detail": "User unidentified and not authorized"},
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            
            # Attach the identifier to the request state to use in other middlewares
            request.state.user_identifier = user_identifier
            request.state.user_roles=user_roles
            request.state.role_version=role_version

        response =  await call_next(request)

        return response