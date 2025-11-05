
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from passlib.context import CryptContext
from backend.auth import SPECIALS  
from jose import jwt, JWTError
from backend.config.settings import config_settings

PASS_HASH_SCHEME=config_settings.PASS_HASH_SCHEME
TOKEN_HASH_ALGO = config_settings.TOKEN_HASH_ALGO
JWT_SECRET = config_settings.JWT_SECRET
JWT_ALGO = config_settings.JWT_ALGO
DEFAULT_ROLE=config_settings.DEFAULT_ROLE

ACCESS_TOKEN_EXPIRE_MINUTES = int(config_settings.ACCESS_TOKEN_EXPIRE_MINUTES)
REFRESH_TOKEN_EXPIRE = int(config_settings.REFRESH_TOKEN_EXPIRE)

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
    

def create_access_token(user_id,user_roles,role_version,expires_dur=ACCESS_TOKEN_EXPIRE_MINUTES):
    now=datetime.now(timezone.utc)
    expiry= now + (timedelta(minutes=expires_dur))
    
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expiry.timestamp()),
        "jti": secrets.token_hex(32),
        "roles": user_roles,
        "role_version":role_version,
    }
    token=jwt.encode(claims=payload,key=config_settings.JWT_SECRET,algorithm=config_settings.JWT_ALGO)
    return token

def generate_plain_token(nbytes: int = 48) -> str:
    return secrets.token_urlsafe(nbytes)

def make_session_token_plain() -> str:
    return generate_plain_token(32)

def make_refresh_plain() -> str:
    return generate_plain_token(48)

def hash_token(plain:str)->str:
    hash_func=getattr(hashlib,TOKEN_HASH_ALGO)
    return hash_func(plain.encode()).hexdigest()

def decode_token(token:str):
    """To verify the signature , expiration and user claims of token"""
    try:
        token_data=jwt.decode(
        jwt=token,
        key=config_settings.JWT_SECRET,
        algorithms=config_settings.JWT_ALGO
        )
        return token_data
    except JWTError as e:
        return None


   
