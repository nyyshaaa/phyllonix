
from typing import Optional
from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from backend.auth.repository import get_device_session_by_pid
from backend.auth.services import save_device_state
from backend.middlewares.constants import logger


# device pid is included in access token . 
# access token is refreshed every few minutes via refresh and device token is validated and attached newly to access token , so every refresh gets current state of device activation .
# use it for paths that need to do something with device id , in case device session got chnaged after attaching it to access token .
class DeviceSessionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, session,paths:str):
        super().__init__(app)
        self.session = session
        self.paths = paths 

    async def dispatch(self, request: Request, call_next):
        if not any(request.url.path.startswith(p) for p in self.paths):
            # Skip device authentication for paths that don't require it
            return await call_next(request)
       
        session_pid = getattr(request.state, "session_pid", None)
        user_id = getattr(request.state, "user_identifier", None)
        
        logger.info("device.middleware.check", extra={
            "path": request.url.path,
            "has_session_pid": bool(session_pid),
            "has_user_id": bool(user_id)
        })

        async with self.session() as session:
            
            if session_pid:
                session_data=await get_device_session_by_pid(session,session_pid,user_id)

                if not session_data:
                    logger.warning("device.middleware.session_not_found", extra={
                        "path": request.url.path,
                        "user_id": user_id
                    })
                    return JSONResponse(
                        {"detail": "User not authorized or session not found"},
                        status_code=status.HTTP_403_FORBIDDEN,
                    )
                
                if session_data["revoked_at"] is not None or session_data["expires_at"] is not None:
                    logger.warning("device.expired_or_revoked",extra={
                        "path": request.url.path,
                        "user_id": user_id
                    })
                    return JSONResponse(
                        {"detail": "Session expired or revoked"},
                        status_code=status.HTTP_403_FORBIDDEN,
                    )

                request.state.sid = session_data["id"]
            
        response = await call_next(request)

        return response