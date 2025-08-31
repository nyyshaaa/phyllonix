
from fastapi import HTTPException
from passlib.context import CryptContext
import re
from email_validator import validate_email, EmailNotValidError
import dns.resolver

from backend.auth import SPECIALS  # for optional MX check

pwd_context = CryptContext(schemes=[PASS_HASH_SCHEME], deprecated="auto")

def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)

def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)

# email syntax validation
def validate_email_syntax(email: str) -> tuple[bool, str]:
    try:
        validated = validate_email(email)  # returns object with normalized form
        return True, validated.email
    except EmailNotValidError as e:
        return False, str(e)

#* reverify
# optional MX check (best-effort, can be slow; use asynchronously or cache)
def has_mx_record(domain: str) -> bool:
    try:
        answers = dns.resolver.resolve(domain, "MX")
        return len(answers) > 0
    except Exception:
        return False

#* check return styles 
def validate_password_policy(password: str, min_length: int = 8) -> tuple[bool, str]:
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

def validate_signup_data(payload):
    ok, email_or_err = validate_email_syntax(payload.email)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Invalid email: {email_or_err}")
    normalized_email = email_or_err

    # optional: check MX
    domain = normalized_email.split("@", 1)[1]
    if not has_mx_record(domain):
        # Warning: MX checks can block legitimate emails (e.g., gmail always OK, but some domains have no MX but accept mail)
        # You can decide to warn instead of reject; here we reject for stronger validation
        raise HTTPException(status_code=400, detail="Email domain appears invalid (no MX records)")
    
    # 2. Validate password policy
    ok, message = validate_password_policy(payload.password, min_length=8)
    if not ok:
        raise HTTPException(status_code=400, detail=message)