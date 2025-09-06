
import asyncio
from pathlib import Path
from typing import Tuple
from sqlalchemy import text
from backend.user import constants
# from backend.user.constants import PROFILE_ROOT_PATH, MEDIA_ROOT, THUMB_ROOT_PATH, THUMB_SIZE
from PIL import Image, UnidentifiedImageError
from backend.db.connection import async_session
from backend.user.utils import file_hash
from backend.config.media_config import media_settings
from backend.__init__ import logger

FILE_SECRET_KEY=media_settings.FILE_SECRET_KEY

CLAIM_BATCH_SQL = text("""
WITH cte AS (
  SELECT id
  FROM usermedia
  WHERE profile_image_url IS NOT NULL AND (profile_image_thumb_url IS NULL)
  FOR UPDATE SKIP LOCKED
  LIMIT :limit
)
UPDATE usermedia
SET profile_image_thumb_url = :marker
FROM cte
WHERE usermedia.id = cte.id
RETURNING usermedia.id, usermedia.profile_image_url
""")
UPDATE_ROW_SQL = text("UPDATE usermedia SET profile_image_thumb_url = :thumb_path WHERE id = :id AND user_id =:user_id")
MARK_FAILED_SQL = text("UPDATE usermedia SET profile_image_thumb_url = NULL WHERE id = :id AND user_id =:user_id")
SELECT_MEDIA_ID=text("SELECT usermedia.id FROM usermedia WHERE id=:id")


class ThumbnailWorker:

    MEDIA_ROOT = media_settings.MEDIA_ROOT
    PROFILE_ROOT_PATH = media_settings.PROFILE_IMG_PATH
    THUMB_ROOT_PATH=media_settings.THUMBNAIL_IMG_PATH
    THUMB_SIZE = (300, 300)
    FORMAT="jpeg"

    async def thumbnail_worker_loop(self):
        logger.info("Thumbnail worker started, waiting for tasks...")
        processed=0
        while True:
            try:
                task = await constants.tasks_queue.get()
                if task is None:
                    # sentinel to shutdown
                    logger.info("Thumbnail worker shutting down")
                    break

                user_id = task["user_id"]
                media_id = task["media_id"]
                rel_path = task["rel_path"]

                logger.info("[worker] picked task user=%s row=%s", user_id, media_id)

                processed += await self.process_thumbnail_task(media_id, user_id,rel_path,async_session)
            except Exception:
                logger.exception("[worker] unexpected error handling task: %s", task)
                # avoid losing the item forever; mark done to prevent blocking if you've chosen to
                try:
                    constants.tasks_queue.task_done()
                except Exception:
                    pass

        logger.info("[worker] processed task user=%s row=%s processed=%s", user_id, media_id, processed)

    # --- processing logic (async, but offloads blocking parts to threads) ---
    async def process_single_row_async(self,row_id: int, image_rel: str) -> Tuple[int, str]:
        src = ThumbnailWorker.MEDIA_ROOT / Path(ThumbnailWorker.PROFILE_ROOT_PATH) / image_rel
        # log(src, "processing row", row_id)
        if not src.exists():
            raise FileNotFoundError("source missing: %s" % src)

        # blocking open+resize in thread
        thumb_img, fmt = await asyncio.to_thread(self._open_and_resize_sync, src, ThumbnailWorker.THUMB_SIZE)

        # choose thumbnail path
        rel_thumb=f"{file_hash(row_id,FILE_SECRET_KEY)}.{ThumbnailWorker.FORMAT}"
        thumb_dir=Path(ThumbnailWorker.THUMB_ROOT_PATH)/rel_thumb
        abs_thumb_dir=Path(ThumbnailWorker.MEDIA_ROOT)/thumb_dir
        
        # save in thread (blocking)
        await asyncio.to_thread(self._save_atomic_sync, thumb_img, abs_thumb_dir, 
                                ThumbnailWorker.FORMAT, 85)

        return row_id, str(rel_thumb)

    async def process_thumbnail_task(self,row_id,user_id,img_rel,async_session):
        processed = 0
        async with async_session() as session:
            res=await session.execute(SELECT_MEDIA_ID,{"id":row_id})
        if not res:
            logger.error("cannot process object with id None")
            return 0
        try:
            _, rel_thumb = await self.process_single_row_async(row_id, img_rel)
            async with async_session() as session:
                await session.execute(UPDATE_ROW_SQL, {"thumb_path": rel_thumb, "id": row_id,"user_id":user_id})
                await session.commit()
            processed = 1
            logger.info("Processed %s -> %s", row_id, rel_thumb)
            return processed
        except FileNotFoundError:
            logger.exception("Missing file for %s, clearing marker", row_id)
            async with async_session() as session:
                await session.execute(MARK_FAILED_SQL, {"id": row_id,"user_id":user_id})
                await session.commit()
        except UnidentifiedImageError:
            logger.exception("Bad image for %s, clearing marker", row_id)
            async with async_session() as session:
                await session.execute(MARK_FAILED_SQL, {"id": row_id,"user_id":user_id})
                await session.commit()
        except Exception:
            logger.exception("Unexpected error for %s, clearing marker", row_id)
            async with async_session() as session:
                await session.execute(MARK_FAILED_SQL, {"id": row_id,"user_id":user_id})
                await session.commit()
        finally:
            return processed

    # --- blocking helpers (run in threads) ---
    def _open_and_resize_sync(self,src_path: Path, size=(300,300)):
        with Image.open(src_path) as im:
            # do the resize/crop here (release GIL inside Pillow for heavy ops)
            im.thumbnail((max(size), max(size)), Image.LANCZOS)
            w,h = im.size
            tw,th = size
            left = max(0, (w - tw)//2)
            top = max(0, (h - th)//2)
            cropped = im.crop((left, top, left+tw, top+th))
            # return a copy (safe to use outside file context)
            return cropped.copy(), im.format 

    def _save_atomic_sync(self,img: Image.Image, dest: Path, fmt="jpeg", quality=85):
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        img.save(tmp, format=fmt, quality=quality, optimize=True)
        tmp.replace(dest)





