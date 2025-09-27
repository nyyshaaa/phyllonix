import asyncio
import hashlib
import json
import os
import tempfile ,aiofiles
from typing import Tuple
import httpx
from sqlalchemy import select
from backend.__init__ import logger
from backend.schema.full_schema import ImageContent, ImageUploadStatus, ProviderWebhookEvent
from sqlalchemy import text, select
from backend.db.connection import async_session

class ImageTransformHandler():
 
    def __init__(self, max_download_size: int = 50 * 1024 * 1024, http_retries: int = 2):
            self.max_download_size = max_download_size
            self.http_retries = http_retries

    async def compute_checksum_and_update_status(self,event,w_name):

        provider_payload = event.get("payload")
        event_id=event.get("event_id")
        logger.info("[%s] processing provider_event=%s", w_name, event_id)


        async with async_session() as session:
           
            event_row=None

            try:
                stmt = text("SELECT id, processed_at, attempts FROM provider_webhook_events WHERE event_id = :eid FOR UPDATE")
                res = await session.execute(stmt, {"eid": event_id})  
                event_row=res.first()
            except Exception:
                logger.exception("Failed to fetch provider_event %s", event_id)
                raise

            if not event_row:
                logger.warning("[%s] provider_event missing %s — nothing to do", w_name, event_id)
                return
            
            evt_id, processed_at, attempts = event_row[0], event_row[1], event_row[2]
            if processed_at:
                logger.info("[%s] event %s already processed at %s — skipping", w_name, event_id, processed_at)
                return
            
            product_image=event.get("product_image")
            
            # if prod image already linked to image content and status ready then skip and mark in webhooks table 
            await self.is_image_processed(session,product_image,w_name,evt_id)

            tmp_path, checksum = await self.download_n_checksum(session,provider_payload,w_name,evt_id)
            
            content_id=await self.image_content_insert(session,product_image,provider_payload,checksum,w_name)

            await self.link_to_prod_img(session,product_image,content_id,evt_id,w_name)

            # do any processing with the temp file if needed after updating image content and product image tables
            # enqueue further processing  in separate subscriber (e.g. create thumbnails, variants, etc.)
            
    async def is_image_processed(self,session,product_image,w_name,evt_id):
        if product_image.content_id is not None and product_image.status == ImageUploadStatus.READY:
            logger.info("[%s] product_image %s already processed (content_id=%s) — skipping", w_name, product_image.id, product_image.content_id)
            # Mark event processed for safety:
            await session.execute(text("UPDATE provider_webhook_events SET processed_at = now() WHERE id = :id"), {"id": evt_id})
            await session.commit()
            return
        
    async def download_n_checksum(self,session,provider_payload,w_name,evt_id):
        last_exc = None
        checksum = None
        for attempt in range(self.http_retries + 1):
            try:
                url = provider_payload.get("secure_url") or provider_payload.get("url")
                tmp_path, checksum = await self.download_to_tempfile_and_checksum(url)
                return tmp_path, checksum
            except Exception as e:  #** do it for some specific exceptions only
                last_exc = e
                logger.warning("[%s] download attempt %d failed for %s: %s", w_name, attempt+1, evt_id, e)
                await asyncio.sleep(1 + attempt * 2)
        if checksum is None:
            # record failure attempts and potentially escalate
            await session.execute(text("UPDATE provider_webhook_events SET attempts = COALESCE(attempts,0)+1 WHERE id = :id"), {"id": evt_id})
            await session.commit()
            logger.exception("[%s] failed to download content for %s after retries", w_name, evt_id)
            # optionally push to DLQ after few retries if still fails
            return
        
    async def image_content_insert(self,session,product_image,provider_payload,checksum,w_name):
        try:
            insert_sql = text("""
                INSERT INTO imagecontent (checksum, provider_public_id, url, meta)
                VALUES (:checksum, :ppid, :url, :meta::jsonb)
                ON CONFLICT (checksum) DO NOTHING
                RETURNING id, public_id;
            """)
            meta = {}  # add whatever metadata you want: width, height, format
            res = await session.execute(insert_sql, {
                "checksum": checksum,
                "ppid": provider_payload.get("asset_id") or provider_payload.get("public_id"),
                "url": provider_payload.get("secure_url") or provider_payload.get("url"),
                "meta": json.dumps(meta)
            })
            row = res.first()
            if row:
                content_id = row[0]
                content_public_id = row[1]
            else:
                # someone else created canonical row: select it
                sel = select(ImageContent).where(ImageContent.checksum == checksum)
                res = await session.execute(sel)
                existing = res.scalar_one_or_none()
                if not existing:
                    # This is unexpected but handle gracefully
                    logger.exception("[%s] canonical imagecontent missing after insert conflict for %s", w_name, checksum)
                    # create fallback or raise
                    raise RuntimeError("canonical imagecontent missing")
                content_id = existing.id
                content_public_id = existing.public_id

            return content_id

        except Exception:
            logger.exception("[%s] failed to upsert/select imagecontent for %s", w_name, checksum)
            raise

    async def link_to_prod_img(self,session,product_image,content_id,evt_id,w_name):
        try:
            await session.execute(text("""
                UPDATE product_image
                SET content_id = :cid,
                    status = :ready,
                    processed_at = now()
                WHERE id = :pid AND content_id IS NULL
            """), {"cid": content_id, "ready": ImageUploadStatus.READY, "pid": product_image.id})
            # mark event processed
            await session.execute(text("""
                UPDATE provider_webhook_events
                SET processed_at = now()
                WHERE id = :id
            """), {"id": evt_id})
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("[%s] failed to link product_image -> imagecontent for %s", w_name, product_image.id)
            raise

    async def download_to_tempfile_and_checksum(self,
        url: str,
        timeout_seconds: float = 60.0
    ) -> Tuple[str, str]:
        """
        Stream-download `url` into a temp file using async I/O, computing SHA256 on the fly.
        Returns (temp_path, sha256_hex). Caller must remove temp_path when done.
        Raises on HTTP errors, or if file exceeds max_bytes.
        """

        # create temp path first, open with aiofiles for async writes
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp_path = tmp.name
        tmp.close()  # we'll use aiofiles to (async) write to this path

        sha = hashlib.sha256()
        total = 0
        timeout = httpx.Timeout(timeout_seconds, connect=15.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                try:
                    async with aiofiles.open(tmp_path, "wb") as afp:
                        async for chunk in resp.aiter_bytes():
                            if not chunk:
                                continue
                            total += len(chunk)
                            if total > self.max_bytes:
                                # cleanup and raise
                                await afp.close()
                                try:
                                    os.remove(tmp_path)
                                except Exception:
                                    logger.exception("Failed to remove oversize tempfile %s", tmp_path)
                                raise ValueError(f"Downloaded file exceeds max_bytes ({self.max_bytes})")
                            # write chunk to disk
                            await afp.write(chunk)
                            # update checksum
                            sha.update(chunk)
                except Exception:
                    # If write fails, ensure tmp cleaned up
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        logger.exception("Failed to cleanup tempfile after failure %s", tmp_path)
                    raise

        return tmp_path, sha.hexdigest()




