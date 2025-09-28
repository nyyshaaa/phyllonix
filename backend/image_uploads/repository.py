
from datetime import datetime, timezone
import json
from fastapi import HTTPException, Response
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError,OperationalError, DatabaseError
from backend.__init__ import logger
from backend.schema.full_schema import ImageUploadStatus, ProductImage 


async def create_webhook_event(session, provider_event_id, payload):

    """Persist raw webhook event for idempotency + audit/replay (provider_webhook_events table)"""
    event_row=None
    try:
        insert_sql = text("""
            INSERT INTO providerwebhookevent (provider_event_id, provider, payload, received_at)
            VALUES (:peid, :prov, CAST(:payload AS jsonb), now())
            ON CONFLICT (provider_event_id) DO NOTHING
            RETURNING id,processed_at;
        """)
        res = await session.execute(insert_sql, {"peid": provider_event_id, "prov": "cloudinary", "payload": json.dumps(payload)})
        await session.commit()
        event_row = res.first()

        if event_row is None:
            select_sql = text("""
                SELECT id, processed_at FROM providerwebhookevent WHERE provider_event_id = :peid
            """)
            res = await session.execute(select_sql, {"peid": provider_event_id})
            event_row = res.first()
            await session.commit()
        return event_row
    
    except IntegrityError as e:
        print(e)
        print("integrity issue")
        await session.rollback()
        return event_row
        
    except (OperationalError, DatabaseError) as db_err:
        # Transient DB problem: log and return 5xx so provider retries
        logger.exception("Transient DB error while persisting webhook event %s - returning 500 to allow retry", provider_event_id)
        raise HTTPException(status_code=500, detail="temporary database error")
    

async def update_prod_image_upload_status(session,product_image):
    # update fields
    stmt=(update(ProductImage).where(ProductImage.id == product_image.id).values(
        # provider_public_id = payload.get("asset_id") or public_id,
        # url = payload.get("secure_url") or payload.get("url") or product_image.url,
        status = ImageUploadStatus.UPLOADED,
        updated_at = datetime.now(timezone.utc)).returning(ProductImage.id)
        )
    res=await session.execute(stmt)
    await session.commit()
    res=res.first()
    return res

async def get_image_by_cloud_pkey(session,public_id,folder):

    product_image = None
    if folder.startswith("images/"):
        parts = folder.split("/", 1)
        if len(parts) == 2:
            prod_img_public_id = parts[1]
            stmt = select(ProductImage).where(ProductImage.public_id == prod_img_public_id)
            r = await session.execute(stmt)
            product_image = r.scalar_one_or_none()

    if product_image is None and public_id:
        stmt = select(ProductImage).where(ProductImage.storage_key.like(f"%/{public_id}"))
        r = await session.execute(stmt)
        product_image = r.scalar_one_or_none()

    return product_image
    

    
    