
from fastapi import Request,HTTPException,status
from fastapi.security import HTTPBearer , http

from jose import jwt, JWTError
from backend.config.settings import config_settings


class Authentication(HTTPBearer):
    def __init__(self,auto_error=True): 
        super().__init__(auto_error=auto_error)

    async def __call__(self, request:Request) -> http.HTTPAuthorizationCredentials|None:
        auth_creds=await super().__call__(request)
        token=auth_creds.credentials

        decoded_token=self.decode_token(token)

        if not decoded_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Invalid or expired token provided.")
        
        return decoded_token
    
    def decode_token(self,token:str):
        """To verify the signature , expiration and user claims of token"""
        try:
            token_data=jwt.decode(
            token,
            key=config_settings.JWT_SECRET,
            algorithms=config_settings.JWT_ALGO
            )
            return token_data
        except JWTError as e:
            return None


