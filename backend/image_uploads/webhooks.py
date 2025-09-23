
import os
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from backend.db.dependencies import get_session
from backend.image_uploads.dependency import validate_upload_signature
from backend.schema.full_schema import ProductImage
from backend.config.media_config import CLOUDINARY_CALLBACK_ROUTE
from backend.__init__ import logger

uploads_router = APIRouter()


@uploads_router.post(f"/{CLOUDINARY_CALLBACK_ROUTE}")
async def cloudinary_webhook(body_bytes=Depends(validate_upload_signature), session = Depends(get_session)):
    
    # parse JSON body now that signature is validated

    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception:
        logger.exception("Invalid JSON payload")
        raise HTTPException(status_code=400, detail="invalid json")
   
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