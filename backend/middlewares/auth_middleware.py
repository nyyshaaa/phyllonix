
from typing import Optional
from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from backend.user.dependencies import Authentication
from backend.user.repository import userid_by_public_id


class AuthenticationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, session,paths:str):
        super().__init__(app)
        self.session = session
        self.paths = paths 

    async def dispatch(self, request: Request, call_next):
        if any(request.url.path.startswith(p) for p in self.paths):
            # Skip authentication for paths that don't require it
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
        # ds_id = int(auth_token.get("sid"))   
    
        #* ignore ds id for now in access token , create device session at first user interaction and use device session checks at login ,
        # also link device session to user on login , when user logs out revoke device session and remove from browser interface / or keep it don't revoke until expiry.
        # revoke in case of suspicious activity.

        async with self.session() as session:
            # ds = await device_active(session,ds_id)
            # if not ds:
            #     return JSONResponse(
            #         {"detail": "Device not authorized"},
            #         status_code=status.HTTP_403_FORBIDDEN,
            #     )
            
            identifier = await userid_by_public_id(session,user_pid)
            if not identifier:
                return JSONResponse(
                    {"detail": "User not authorized"},
                    status_code=status.HTTP_403_FORBIDDEN,
                )

            # Attach the identifier to the request state to use in other middlewares
            request.state.user_identifier = identifier
            request.state.user_roles=user_roles


        return await call_next(request)