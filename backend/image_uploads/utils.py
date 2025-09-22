
import hashlib
import hmac


def compute_notification_signature_sha1(body_bytes: bytes, timestamp: str, api_secret: str) -> str:
    """
    Cloudinary notification signature: SHA1(hex) of (raw_body + timestamp + api_secret)
    """
    to_sign = body_bytes + timestamp.encode("utf-8") + api_secret.encode("utf-8")
    return hashlib.sha1(to_sign).hexdigest()


def secure_compare(a: str, b: str) -> bool:
    # constant-time compare
    return hmac.compare_digest(a, b)
