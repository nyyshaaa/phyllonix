
import asyncio
from pathlib import Path
from typing import Tuple
from sqlalchemy import text
from PIL import Image, UnidentifiedImageError
from backend.background_workers.repository import MARK_FAILED_SQL, SELECT_MEDIA_ID, UPDATE_ROW_SQL
from backend.db.connection import async_session
from backend.user.utils import file_hash
from backend.config.media_config import media_settings
from backend.__init__ import logger

FILE_SECRET_KEY=media_settings.FILE_SECRET_KEY

class ThumbnailTaskHandler:

    MEDIA_ROOT = media_settings.MEDIA_ROOT
    PROFILE_ROOT_PATH = media_settings.PROFILE_IMG_PATH
    THUMB_ROOT_PATH=media_settings.THUMBNAIL_IMG_PATH
    THUMB_SIZE = (300, 300)
    FORMAT="jpeg"

    async def thumbgen(self,task,w_name):
        user_id = task["user_id"]
        media_id = task["media_id"]
        rel_path = task["rel_path"]

        logger.debug("[%s] picked task user=%s media=%s rel=%s", w_name, user_id, media_id, rel_path) 
        
        await self.process_thumbnail_task(media_id, user_id,rel_path,async_session)
        
    async def log_analytics(self):
        await asyncio.sleep(1)
        return 1

    async def notify_admin(self):
        await asyncio.sleep(2)
        return 1


    # --- processing logic (async, but offloads blocking parts to threads) ---
    async def process_single_row_async(self,row_id: int, image_rel: str) -> Tuple[int, str]:
        src = ThumbnailTaskHandler.MEDIA_ROOT / Path(ThumbnailTaskHandler.PROFILE_ROOT_PATH) / image_rel
        # log(src, "processing row", row_id)
        if not src.exists():
            raise FileNotFoundError("source missing: %s" % src)

        # blocking open+resize in thread
        thumb_img, fmt = await asyncio.to_thread(self._open_and_resize_sync, src, ThumbnailTaskHandler.THUMB_SIZE)

        # choose thumbnail path
        rel_thumb=f"{file_hash(row_id,FILE_SECRET_KEY)}.{fmt}"
        thumb_dir=Path(ThumbnailTaskHandler.THUMB_ROOT_PATH)/rel_thumb
        abs_thumb_dir=Path(ThumbnailTaskHandler.MEDIA_ROOT)/thumb_dir
        
        # save in thread (blocking)
        await asyncio.to_thread(self._save_atomic_sync, thumb_img, abs_thumb_dir, 
                                fmt, 85)

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
                print("worker loop here ")
                await session.execute(UPDATE_ROW_SQL, {"thumb_path": rel_thumb, "id": row_id,"user_id":user_id})
                await session.commit()
            processed = 1
            logger.debug("Processed %s -> %s", row_id, rel_thumb)
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





