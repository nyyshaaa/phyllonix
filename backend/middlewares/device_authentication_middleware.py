
from typing import Optional
from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from backend.auth.repository import identify_device_session
from backend.auth.services import save_device_state

# this middleware will run only for endpoints that don't require auth otherwise device checks will happen at user authetication stage and ttached to request state
class DeviceSessionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, session,paths:str):
        super().__init__(app)
        self.session = session
        self.paths = paths 

    async def dispatch(self, request: Request, call_next):
        # cookie in browsers, fallback to header (mobile app)
        device_session_plain = request.cookies.get("px_device") or request.headers.get("X-Device-Token")
        
        user_id = getattr(request.state, "user_identifier", None)
        session_id = getattr(request.state, "sid", None)

        if session_id:
            return await call_next(request)

        set_cookie_later=False


        # device lookup / create
        async with self.session() as session:
            
            if device_session_plain:
                session_id=await identify_device_session(session,device_session_plain)


            # implies token not prsent in cookie(first time interaction) or is invalid(cookie state corrupted) or it is revoked  (set cookie with new token in all cases)
            # create device session 
            if not device_session_plain or not session_id :
                session_id,device_session_plain=await save_device_state(session,request,user_id)
                await session.commit()
                set_cookie_later=True


            # attach to request
            request.state.sid = session_id

            # schedule async update of last_seen (non-blocking) if to be updated
            # either enqueue background task or do conditional update
            
            
        # call handler
        response = await call_next(request)

        # set cookie if we created device
        if set_cookie_later:
            response.set_cookie(
                key="px_device",
                value=device_session_plain,
                httponly=True,
                secure=True,
                samesite="Lax",
                max_age=60 * 60 * 24 * 90,
            )

        return response