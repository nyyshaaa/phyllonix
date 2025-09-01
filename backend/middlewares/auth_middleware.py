
from typing import Optional
from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from backend.user.dependencies import Authentication
from backend.user.repository import device_active, userid_by_public_id


class AuthenticationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, session):
        super().__init__(app)
        self.session = session
        # self.paths = paths 

    async def dispatch(self, request: Request, call_next):
        # if any(request.url.path.startswith(p) for p in self.paths):
        #     # Skip authentication for paths that don't require it
        #     return await call_next(request)
        
        #** chnage this to if else block later and Authentiction auto error false
        try:
            auth_token = await Authentication()(request)
        except Exception as e:
            return JSONResponse(
                {"detail": "Missing or Invalid Auth Headers"},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        
        user_pid = int(auth_token.get("sub"))
        ds_id = int(auth_token.get("sid"))

        async with self.session() as session:
            ds = await device_active(session,ds_id)
            if not ds:
                return JSONResponse(
                    {"detail": "Device not authorized"},
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            
            identifier = await userid_by_public_id(session,user_pid)
            if not identifier:
                return JSONResponse(
                    {"detail": "User not authorized"},
                    status_code=status.HTTP_403_FORBIDDEN,
                )

            # Attach the identifier to the request state to use in other middlewares
            request.state.user_identifier = identifier


        return await call_next(request)