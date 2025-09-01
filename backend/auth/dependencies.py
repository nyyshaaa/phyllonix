import http
import dns
from email_validator import validate_email, EmailNotValidError
from fastapi import HTTPException, Request,status
from fastapi.security import HTTPBearer

from backend.auth.utils import decode_token, validate_password





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

async def signup_validation(payload):
    # 1) validate & normalize email
    try:
        email = normalize_email_address(payload.email)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid email: {e}")

    # optional MX check (non-blocking decision)
    domain = email.split("@", 1)[1]
    if not maybe_check_mx(domain):
        # MX missing doesn't always mean invalid mailboxes; warn or reject as you prefer.
        # Here we reject to enforce stronger correctness; change to log/warn if you prefer.
        raise HTTPException(status_code=400, detail="Email domain does not accept mail (no MX record)")

    is_valid, status = validate_password(payload.password)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=status)
    
    return payload
    