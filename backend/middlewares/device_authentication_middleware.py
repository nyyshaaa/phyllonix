
from typing import Optional
from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from backend.auth.repository import get_device_session
from backend.auth.services import save_device_state

# this middleware will run only for endpoints that don't require auth otherwise device checks will happen at user authetication stage and ttached to request state
class DeviceSessionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, session,paths:str):
        super().__init__(app)
        self.session = session
        self.paths = paths 

    async def dispatch(self, request: Request, call_next):
        if not any(request.url.path.startswith(p) for p in self.paths):
            # Skip device authentication for paths that don't require it
            return await call_next(request)
       
        device_session_plain = request.cookies.get("session_token") or request.headers.get("X-Device-Token")
        user_id = getattr(request.state, "user_identifier", None)
        
        # session_id = getattr(request.state, "sid", None)
        # if session_id:
        #     return await call_next(request)

        async with self.session() as session:
            
            if device_session_plain:
                session_data=await get_device_session(session,device_session_plain,user_id)

                if not session_data:
                    return JSONResponse(
                        {"detail": "User not authorized or session not found"},
                        status_code=status.HTTP_403_FORBIDDEN,
                    )
                
                if session_data["revoked_at"] is not None or session_data["expires_at"] is not None:
                    return JSONResponse(
                        {"detail": "Session expired or revoked"},
                        status_code=status.HTTP_403_FORBIDDEN,
                    )

                request.state.sid = session_data["id"]
            
        response = await call_next(request)

        return response