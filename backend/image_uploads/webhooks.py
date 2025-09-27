
import os
import json
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import select
from backend.db.dependencies import get_session
from backend.image_uploads.dependency import validate_upload_signature
from backend.image_uploads.repository import create_webhook_event, update_prod_image_upload_status
from backend.schema.full_schema import ProductImage
from backend.config.media_config import media_settings
from backend.__init__ import logger
from backend.image_uploads.services import enqueue_process_simulate

uploads_router = APIRouter()

CLOUDINARY_CALLBACK_ROUTE = media_settings.CLOUDINARY_CALLBACK_ROUTE  


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

    event_row=await create_webhook_event(session,provider_event_id,payload)

    if event_row.prcocessed_at:
        logger.info("Event %s already processed at %s - skipping", provider_event_id, event_row.processed_at)
        return Response(status_code=200)

    # Map payload to ProductImage row
    public_id = payload.get("public_id")
    folder = payload.get("folder", "")  # if you set folder param in init it should be images/<product_img_public_id>
    product_image = None


    if folder.startswith("images/"):
        try:
            parts = folder.split("/", 1)
            if len(parts) == 2:
                prod_img_public_id = parts[1]
                stmt = select(ProductImage).where(ProductImage.public_id == prod_img_public_id)
                qres = await session.execute(stmt)
                product_image = qres.scalar_one_or_none()
        except Exception:
            logger.exception("Failed to lookup ProductImage by folder")

    if product_image:
        try:
           
            updated_id=await update_prod_image_upload_status(session,product_image)

            if not updated_id:
                logger.error("Failed to update ProductImage status for id %s", product_image.id)
                raise HTTPException(status_code=500, detail="Failed to update product image status")
                
            # enqueue heavy processing (worker will compute checksum, canonicalize, create variants, etc.)
            enqueue_process_simulate("process_image", {"product_image_public_id": product_image.public_id, "provider_asset_id": payload.get("asset_id") or payload.get("public_id")})
            logger.info("Enqueued process_image for %s", product_image.public_id)

            return Response(status_code=200)
        except Exception:
            logger.exception("Failed to update product_image or enqueue job")
            # we still return 200 because webhook will be retried by Cloudinary; ensure idempotency in processing
            return Response(status_code=200)
    