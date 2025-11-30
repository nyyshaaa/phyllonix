
from typing import Optional
import dns
from email_validator import validate_email, EmailNotValidError
from fastapi import Body, HTTPException, Header, Request,status
from fastapi.params import Cookie
from backend.auth.constants import COOKIE_NAME
from backend.auth.utils import  hash_token, make_session_token_plain, validate_password
from backend.auth.constants import logger


def normalize_email_address(email: str) -> str:
    """
    Validate and return normalized email (lowercased, normalized by email-validator).
    Raises ValueError if invalid.
    """
    try:
        v = validate_email(email)
        return v.email.lower()
    except EmailNotValidError as e:
        raise ValueError(str(e))

# optional mx check
# try:
#     import dns.resolver
#     DNS_AVAILABLE = True
# except Exception:
#     DNS_AVAILABLE = False

def maybe_check_mx(domain: str) -> bool:
    # if not DNS_AVAILABLE:
    #     return True  # can't check, assume ok
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=5.0)
        return len(answers) > 0
    except Exception:
        return False

async def signup_validation(payload=Body(...)):
    # 1) validate & normalize email
    try:
        email = normalize_email_address(payload["email"])
    except ValueError as e:
        logger.warning("signup.validation.email_invalid", extra={"email": payload.get("email"), "error": str(e)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid email: {e}")

    # optional MX check (non-blocking decision)
    # domain = email.split("@", 1)[1]
    # if not maybe_check_mx(domain):
    #     # MX missing doesn't always mean invalid mailboxes; warn or reject as you prefer.
    #     # Here we reject to enforce stronger correctness; change to log/warn if you prefer.
    #     raise HTTPException(status_code=400, detail="Email domain does not accept mail (no MX record)")

    is_valid, detail = validate_password(payload["password"])
    if not is_valid:
        logger.warning("signup.validation.password_invalid", extra={"email": email, "reason": detail})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    
    return payload
    
#** dev mode compatible until frontend is added
#** change it to cookies for mobile and web browsers . 

def device_session_plain(device_header: Optional[str] = Header(None, alias="X-Device-Token"),
                         device_cookie:Optional[str]=Cookie(None,alias="session_token")):
    return device_header or device_cookie

def device_session_pid(device_header: Optional[str] = Header(None, alias="X-Device-Id"),
                         device_cookie:Optional[str]=Cookie(None,alias="device_public_id")):
    return device_header or device_cookie

def refresh_token(refresh_header: Optional[str] = Header(None, alias="X-Refresh-Token"),
                refresh_cookie:Optional[str]=Cookie(None,alias=COOKIE_NAME)):
    return refresh_header or refresh_cookie

