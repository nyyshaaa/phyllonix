
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from passlib.context import CryptContext
from email_validator import validate_email, EmailNotValidError
import dns.resolver
from backend.auth import SPECIALS  
import uuid
from jose import jwt, JWTError
from backend.config.settings import config_settings


JWT_SECRET = config_settings.JWT_SECRET
JWT_ALGO = config_settings.JWT_ALGO
ACCESS_TOKEN_EXPIRE_MINUTES = int(config_settings.ACCESS_TOKEN_EXPIRE_MINUTES)
REFRESH_TOKEN_EXPIRE_DAYS = int(config_settings.REFRESH_TOKEN_EXPIRE_DAYS)

pwd_context = CryptContext(schemes=[PASS_HASH_SCHEME], deprecated="auto")

def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)

def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def validate_password(password: str, min_length: int = 8) -> tuple[bool, str]:
    pw = password.strip()
    if len(pw) < min_length:
        return False, f"Password must be at least {min_length} characters long"
    if not any(c.islower() for c in pw):
        return False, "Password must include at least one lowercase letter"
    if not any(c.isupper() for c in pw):
        return False, "Password must include at least one uppercase letter"
    if not any(c.isdigit() for c in pw):
        return False, "Password must include at least one digit"
    if not any(c in SPECIALS for c in pw):
        return False, "Password must include at least one special character"
    return True, "OK"
    
#** add sid as well
def create_token(user_identity:dict,expires_time:timedelta=None,refresh:bool=False):
    payload={}
    expiry=datetime.now() + (expires_time or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

    payload["user"]=user_identity
    payload["exp"]=expiry
    payload["jti"]=str(uuid.uuid4())
    payload["refresh"]=refresh

    token=jwt.encode(payload=payload,key=config_settings.JWT_SECRET,algorithm=config_settings.JWT_ALGO)
    return token


   
