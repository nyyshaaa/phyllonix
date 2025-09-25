

from datetime import datetime, timezone
import os
from fastapi import HTTPException, Request
from backend.config.media_config import media_settings
from backend.image_uploads.utils import compute_notification_signature_sha1
from backend.image_uploads.utils import secure_compare

MAX_WEBHOOK_AGE_SECONDS = int(os.getenv("CLOUDINARY_WEBHOOK_MAX_AGE", 2 * 60 * 60))

CLOUDINARY_API_SECRET=media_settings.CLOUDINARY_API_SECRET


async def validate_upload_signature(request:Request):
    body_bytes = await request.body()
    incoming_sig = request.headers.get("X-Cld-Signature") or request.headers.get("x-cld-signature")
    incoming_ts = request.headers.get("X-Cld-Timestamp") or request.headers.get("x-cld-timestamp")

    if not incoming_sig or not incoming_ts:
        raise HTTPException(status_code=400, detail="Missing Cloudinary webhook signature/timestamp")

    # verify freshness (to mitigate replay)
    try:
        ts_int = int(incoming_ts)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid X-Cld-Timestamp")

    now_ts = int(datetime.now(timezone.utc).timestamp())
    if abs(now_ts - ts_int) > MAX_WEBHOOK_AGE_SECONDS:
        raise HTTPException(status_code=400, detail="Stale webhook timestamp")

    expected_sha1 = compute_notification_signature_sha1(body_bytes, incoming_ts, CLOUDINARY_API_SECRET)
    
    # secure compare (constant time)
    if not (secure_compare(incoming_sig, expected_sha1)):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")
    
    return body_bytes
