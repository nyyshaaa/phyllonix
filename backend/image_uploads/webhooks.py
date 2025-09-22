
import os
import json
import hashlib
import hmac
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, HTTPException, Response, Depends
from sqlalchemy import text
from sqlmodel import select
from backend.db.dependencies import get_session
from backend.image_uploads.dependency import validate_upload_signature
from backend.products.routes import prods_admin_router
from backend.schema.full_schema import ImageUploadStatus, ProductImage


@prods_admin_router.post("/webhooks/cloudinary")
async def cloudinary_webhook(body_bytes=Depends(validate_upload_signature), session = Depends(get_session)):
    
    # parse JSON body now that signature is validated
    payload = json.loads(body_bytes.decode("utf-8"))

    # dedupe provider webhook events: prefer asset_id if present or use public_id:version
    provider_event_id = payload.get("asset_id") or f"{payload.get('public_id')}:{payload.get('version')}"

    # Map payload to ProductImage row
    public_id = payload.get("public_id")
    folder = payload.get("folder", "")  # if you set folder param in init it should be images/<product_img_public_id>
    product_image = None

    if folder.startswith("images/"):
        parts = folder.split("/", 1)
        if len(parts) == 2:
            prod_img_public_id = parts[1]
            stmt = select(ProductImage).where(ProductImage.public_id == prod_img_public_id)
            # update product image 

    # enqueue extra processing work 