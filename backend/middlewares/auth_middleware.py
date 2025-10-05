
from typing import Optional
from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from backend.auth.services import save_device_state
from backend.user.dependencies import Authentication
from backend.user.repository import  userauth_by_public_id, userid_by_public_id


class AuthenticationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, session,paths:str,maybe_auth_paths:Optional[str]):
        super().__init__(app)
        self.session = session
        self.paths = paths 
        # self.maybe_auth_paths=maybe_auth_paths

    async def dispatch(self, request: Request, call_next):
        if any(request.url.path.startswith(p) for p in self.paths):
            # Skip authentication for paths that don't require it
            return await call_next(request)
        
        try:
            auth_token = await Authentication()(request)
        except Exception as e:
            # if any(request.url.path.startswith(p) for p in self.maybe_auth_paths):
            #     return await call_next(request)

            return JSONResponse(
                {"detail": e.detail or "Missing or Invalid Auth Headers"},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        
        user_pid = auth_token.get("sub")
        user_roles=auth_token.get("roles")
        role_version=auth_token.get("role_version")

        device_session_plain = request.cookies.get("px_device") or request.headers.get("X-Device-Token")

    
        # create device session at first user interaction and use device session checks at login ,
        # also link device session to user on login , when user logs out revoke device session and remove from browser interface / or keep it don't revoke until expiry.
        # revoke in case of suspicious activity.

        async with self.session() as session:
            
            user_authdata=await userauth_by_public_id(session,user_pid,device_session_plain)

            print("user_authdata",user_authdata)

            user_identifier=user_authdata.get("user_id")
            if not user_identifier:
                return JSONResponse(
                    {"detail": "User not authorized"},
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            
            sid=user_authdata.get("sid")
            # if sid is None:
            #     pass
            #** create device session and link to user and also populate cookie .

            device_revoked=user_authdata.get("revoked_at")
            if device_revoked is not None:
                return JSONResponse(
                    {"detail": "Device not authorized"},
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            # client should trigger user logout and also revoke refresh token for that user and device .
            
            

            # Attach the identifier to the request state to use in other middlewares
            request.state.user_identifier = user_identifier
            request.state.user_roles=user_roles
            request.state.role_version=role_version
            request.state.sid=sid


            print(user_roles)


        return await call_next(request)