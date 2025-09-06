import hashlib
import hmac 
from pathlib import Path
import time
from backend.config.media_config import media_settings
from PIL import Image
from backend.config.media_config import media_settings

FILE_SECRET_KEY=media_settings.FILE_SECRET_KEY


def file_hash(user_id: int, secret) -> str:
    hash_func=getattr(hashlib,media_settings.HASH_ALGO)
    return hmac.new(secret.encode(), str(user_id).encode(), hash_func).hexdigest()[:16]

class FileUpload:
    MAX_UPLOAD_SIZE = 5 * 1024 * 1024   # 5 MB limit (adjust)
    MEDIA_ROOT = media_settings.MEDIA_ROOT
    PROFILE_ROOT_PATH = media_settings.PROFILE_IMG_PATH
    ALLOWED_TOP_LEVEL = ("image",)      # allow only image/* Content-Type header (quick check)
    CHUNK_SIZE = 1024 * 1024            # 1MB chunk reads

    THUMB_ROOT_PATH = media_settings.THUMBNAIL_IMG_PATH

    FORMAT=".jpg"

    THUMB_SIZE = (300, 300)
    PROCESSING_MARKER = "__PROCESSING__"

    
    def _make_profile_path(self,user_path):
        
        user_dir=Path(FileUpload.PROFILE_ROOT_PATH)/user_path
        dest_dir=Path(FileUpload.MEDIA_ROOT)/user_dir # deterministic for final path
        dest_dir.mkdir(parents=True, exist_ok=True)

        return dest_dir
        
    def _stream_save_to_disk_sync(self,src_file, tmp_path: Path):
        start=time.time()
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        max_size=FileUpload.MAX_UPLOAD_SIZE

        with open(tmp_path, "wb") as w:
            while True:
                chunk = src_file.read(FileUpload.CHUNK_SIZE)
                if not chunk:
                    break
                w.write(chunk)
                total += len(chunk)
                if max_size and total > max_size:
                    try: 
                        w.close()
                    except: 
                        pass
                    tmp_path.unlink(missing_ok=True)
                    raise ValueError("file too large")
        end=time.time()
        print(f"Time taken to save file to disk: {(end-start)*1000} milliseconds")
        return total
    
    def _verify_image_sync(self,tmp_path: Path) -> str:
        start=time.time()
        format=FileUpload.FORMAT
        # tmp_norm = tmp_path.with_suffix(f".norm{format}")
        tmp_norm="test_phase"
        with Image.open(tmp_path) as img:
            img.verify()
            # im = im.convert("RGB")        # drop alpha safely
            # apply EXIF orientation fix here if needed
            # im.save(tmp_norm, format="JPEG", quality=85)
            # tmp_norm.replace(tmp_path)
                
        end=time.time()
        print(f"Time taken to verify image: {(end-start)*1000} milliseconds")
        return tmp_norm,format
    

