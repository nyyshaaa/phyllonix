
from fastapi import Depends, Header, Request,HTTPException,status
from fastapi.security import HTTPBearer , http

from backend.auth.utils import decode_token
from backend.db.dependencies import get_session
from backend.schema.full_schema import DeviceSession,Users


class Authentication(HTTPBearer):
    def __init__(self,auto_error=True): 
        super().__init__(auto_error=auto_error)

    async def __call__(self, request:Request) -> http.HTTPAuthorizationCredentials|None:
        auth_creds=await super().__call__(request)
        token=auth_creds.credentials

        decoded_token=decode_token(token)

        if not decoded_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,details="Invalid or expired token provided.")
        
        return decoded_token


