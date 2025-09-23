
from datetime import datetime, timezone
import json
from fastapi import HTTPException, Response
from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError,OperationalError, DatabaseError
from backend.__init__ import logger
from backend.schema.full_schema import ImageUploadStatus, ProductImage 


async def create_webhook_event(session, provider_event_id, payload):

    """Persist raw webhook event for idempotency + audit/replay (provider_webhook_events table)"""
    
    try:
        insert_sql = text("""
            INSERT INTO provider_webhook_events (provider_event_id, provider, payload, received_at)
            VALUES (:peid, :prov, :payload::jsonb, now())
            ON CONFLICT (provider_event_id) DO NOTHING
            RETURNING id;
        """)
        res = await session.execute(insert_sql, {"peid": provider_event_id, "prov": "cloudinary", "payload": json.dumps(payload)})
        row = res.first()
        await session.commit()
    except IntegrityError:
        # Duplicate event inserted concurrently -> already processed / recorded. Safe: return 200.
        logger.info("Duplicate provider_event_id %s (IntegrityError). Returning 200.", provider_event_id)
        return Response(status_code=200)
    except (OperationalError, DatabaseError) as db_err:
        # Transient DB problem: log and return 5xx so provider retries
        logger.exception("Transient DB error while persisting webhook event %s - returning 500 to allow retry", provider_event_id)
        raise HTTPException(status_code=500, detail="temporary database error")
    # except Exception as exc:
    #     # Unknown error: be conservative and return 500 so provider retries
    #     logger.exception("Unexpected error persisting provider webhook event %s", provider_event_id)
    #     raise HTTPException(status_code=500, detail="internal error")

async def upload_prod_image_upload_status(session,product_image):
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
    

    
    