import hashlib
import hmac
import time
from fastapi import HTTPException , status
from sqlalchemy import select,  update
from backend.schema.full_schema import ImageContent, ImageUploadStatus, ProductImage
from sqlalchemy.exc import IntegrityError
from backend.config.media_config import media_settings
from cloudinary.utils import api_sign_request
from backend.__init__ import logger

CLOUDINARY_UPLOAD_URL = f"https://api.cloudinary.com/v1_1/{media_settings.CLOUDINARY_CLOUD_NAME}/image/upload"


class ImageUpload:
    MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
    ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
    FILE_SECRET_KEY = media_settings.FILE_SECRET_KEY
    FOLDER_PREFIX="images"

    def __init__(self,content_type,filesize,filename,checksum):
        self.content_type=content_type
        self.filesize=filesize
        self.orig_filename=filename
        self.checksum=checksum
        self.ext = self.orig_filename.split(".")[-1].lower() if "." in self.orig_filename else "jpg"

        self._validate_file()

    def _validate_file(self):
        if self.content_type not in ImageUpload.ALLOWED_CONTENT_TYPES:
            raise HTTPException(400, detail=f"content_type {self.content_type} not allowed")
        if self.filesize > ImageUpload.MAX_UPLOAD_BYTES:
            raise HTTPException(413, detail=f"file too large (max {ImageUpload.MAX_UPLOAD_BYTES})")
        
    async def if_image_content_exists(self,session,checksum):
        stmt=select(ImageContent).where(ImageContent.checksum==checksum)
        row=await session.execute(stmt)
        row=row.scalar_one_or_none()
        return row
   
    async def create_image_content(self,session,user_id):
        checksum=self.checksum
       
        img_content=ImageContent(
            checksum=checksum,owner_id=user_id)
        try:
            session.add(img_content)
            await session.commit()
            await session.refresh(img_content)
            return img_content
        except IntegrityError:
            await session.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail="Please retry") # integrity error can happen for same user or different user 
        
    
    async def create_prod_image_link(self,session,product_id,user_id):

        stmt = select(ProductImage).where(
            ProductImage.product_id == product_id,
            ProductImage.orig_filename == self.orig_filename,
            ProductImage.file_size == self.filesize,
            ProductImage.status == ImageUploadStatus.PENDING_UPLOADED
        ).limit(1)
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            return existing
        
        image = ProductImage(
            product_id=product_id,
            storage_key="",
            storage_provider="cloudinary",
            mime_type=self.content_type,
            file_size=self.filesize,
            checksum=None,
            status=ImageUploadStatus.PENDING_UPLOADED,
            orig_filename=self.orig_filename
        )
        
        session.add(image)
        await session.flush()
        await session.refresh(image)
        return image


    def uniq_prod_image_identifier_name(self,prod_image_public_id: str) -> str:
        """
        Deterministic, unguessable storage key
        """
        msg = f"{prod_image_public_id}".encode()
        secret=ImageUpload.FILE_SECRET_KEY
        hash_func = getattr(hashlib, media_settings.HASH_ALGO)
        h = hmac.new(secret.encode(), msg, hash_func).hexdigest()
        # take first 24 hex characters (12 bytes) to keep path shorter but collision-safe
        suffix = h[:24]
        return suffix
    
    async def update_prod_img_storage_key(self,session,prod_image,uniq_img_key):
        storage_key=f"{self.FOLDER_PREFIX}/{prod_image.public_id}/{uniq_img_key}"
        if prod_image.storage_key != storage_key:
            stmt = (
                update(ProductImage)
                .where(ProductImage.id == prod_image.id)
                .values(storage_key=storage_key)
                .returning(ProductImage.id)
            )
            res=await session.execute(stmt)
            await session.commit()
            return res.scalar_one_or_none()
        return True  
    
    async def cloudinary_upload_params(prod_image_public_id: str,unq_img_key:str,expires_in: int = 300):
        timestamp = int(time.time())
        params_to_sign = {"public_id": unq_img_key, "timestamp": timestamp}
        folder=f"{ImageUpload.FOLDER_PREFIX}/{prod_image_public_id}"
        params_to_sign["folder"] = folder
        signature = api_sign_request(params_to_sign, media_settings.CLOUDINARY_API_SECRET)
        response_params = {
            "provider": "cloudinary",
            "upload_url": media_settings.CLOUDINARY_UPLOAD_URL,
            "params": {
                "api_key": media_settings.CLOUDINARY_API_KEY,
                "timestamp": timestamp,
                "signature": signature,
                "public_id": unq_img_key,
                "folder": folder,
                # optional: tell Cloudinary not to create unique filename (we use deterministic public_id)
                "unique_filename": False,
                # # optional: prevent accidental overwrite (set to True or False depending on workflow)
                "overwrite": "false",
            },
            "expires_in": expires_in
        }
        return response_params
    

async def enqueue_process_simulate(job_name: str, payload: dict):
    
    pass
    
    logger.info(f"Simulated enqueue job {job_name} with payload {payload}")
    
    # Fetch ProductImage by public_id (or id) and ensure status is UPLOADED and has a url or provider_public_id.
    # Download asset from provider (Cloudinary secure_url) or via provider API (use retries, timeouts).
    # Insert into ImageContent:
    #     INSERT INTO imagecontent (checksum, owner_id, public_id, provider_public_id, url, meta, created_at) VALUES (...) ON CONFLICT (checksum) DO NOTHING RETURNING id, public_id;
    #     If conflict (row exists), SELECT id, public_id of the existing canonical row.
    # Link ProductImage.content_id to the canonical imagecontent.id and set status = READY (or whatever final status), update processed_at
    # Generate variants (thumbnails, webp, etc.) via image processing pipeline (enqueue sub-jobs for CPU-bound processing / CDN invalidation).
    # Persist variants metadata into ProductImage.variants or ImageContent.meta as appropriate.
    # Update caches / CDN: invalidate or pre-warm if necessary.
    # Metrics/logging: emit processing duration, success/failure, upload sizes, dedupe counts.
    # Cleanup: if the worker detects duplicate provider assets (multiple ProductImage rows mapping to same imagecontent), either mark duplicates as linking to same content and optionally schedule deletion of provider duplicate assets (if you plan to cleanup provider storage).