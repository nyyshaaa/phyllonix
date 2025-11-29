import asyncio
import hashlib
import os
import tempfile ,aiofiles
from typing import Tuple
import httpx
from sqlalchemy import select
from backend.__init__ import logger
from backend.schema.full_schema import ImageContent, ImageUploadStatus, UploadsWebhookEvent
from sqlalchemy import text, select
from backend.db.connection import async_session
from backend.common.utils import now

class ImageTransformHandler():
 
    def __init__(self, max_bytes: int = 50 * 1024 * 1024, http_retries: int = 2):
            self.max_bytes = max_bytes
            self.http_retries = http_retries

    async def compute_checksum_and_update_status(self,event,w_name):

        provider_payload = event.get("payload")
        event_id=event.get("event_id")
        logger.info("[%s] processing provider_event=%s", w_name, event_id)


        async with async_session() as session:
           
            event_row=None

            try:
                stmt = text("SELECT id, processed_at, attempts FROM uploadswebhookevent WHERE id = :eid FOR UPDATE")
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
            await session.execute(text("UPDATE providerwebhookevent SET processed_at = now() WHERE id = :id"), {"id": evt_id})
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
            await session.execute(text("UPDATE providerwebhookevent SET attempts = COALESCE(attempts,0)+1 WHERE id = :id"), {"id": evt_id})
            await session.commit()
            logger.exception("[%s] failed to download content for %s after retries", w_name, evt_id)
            # optionally push to DLQ after few retries if still fails
            return
        
    async def image_content_insert(self,session,product_image,provider_payload,checksum,w_name):
        try:
            image_content = ImageContent(
                checksum=checksum,
                provider_public_id=provider_payload.get("asset_id") or provider_payload.get("display_name"),
                url=provider_payload.get("secure_url") or provider_payload.get("url")
            )
            session.add(image_content)
            try:
                await session.commit()
                await session.refresh(image_content)
                content_id = image_content.id
                content_public_id = image_content.public_id
            except Exception as e:
                await session.rollback()
                # If insert failed due to conflict, fetch existing row
                existing = await session.execute(
                    select(ImageContent).where(ImageContent.checksum == checksum)
                )
                image_content_obj = existing.scalar_one_or_none()
                if not image_content_obj:
                    logger.exception("[%s] canonical imagecontent missing after insert conflict for %s", w_name, checksum)
                    raise RuntimeError("canonical imagecontent missing")
                content_id = image_content_obj.id
                content_public_id = image_content_obj.public_id

            return content_id

        except Exception:
            logger.exception("[%s] failed to upsert/select imagecontent for %s", w_name, checksum)
            raise

    async def link_to_prod_img(self, session, product_image, content_id, evt_id, w_name):
        try:
            product_image.content_id = content_id
            product_image.status = ImageUploadStatus.READY
            session.add(product_image)

            webhook_event = await session.get(UploadsWebhookEvent, evt_id)
            if webhook_event:
                webhook_event.processed_at = now()
                session.add(webhook_event)

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




