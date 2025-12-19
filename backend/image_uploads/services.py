import hashlib
import hmac
import time
from fastapi import HTTPException , status
from pydantic import ValidationError
from sqlalchemy import select,  update
from backend.schema.full_schema import ImageContent, ImageUploadStatus, ProductImage
from sqlalchemy.exc import IntegrityError
from backend.config.media_config import media_settings
from cloudinary.utils import api_sign_request
from backend.__init__ import logger

CLOUDINARY_UPLOAD_URL = f"https://api.cloudinary.com/v1_1/{media_settings.CLOUDINARY_CLOUD_NAME}/image/upload"

class ImageUpload:
    MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
    ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/jpg"}
    FILE_SECRET_KEY = media_settings.FILE_SECRET_KEY
    FOLDER_PREFIX="images"

    def __init__(self,content_type,filesize,filename,sort_order):
        self.content_type=content_type
        self.filesize=filesize
        self.orig_filename=filename
        self.ext = self.orig_filename.split(".")[-1].lower() if "." in self.orig_filename else "jpg"
        self.sort_order=sort_order

        self._validate_file()

    def _validate_file(self):
        if not self.orig_filename:
            raise ValidationError("filename is required")
        if self.filesize <= 0:
            raise ValidationError("filesize must be positive")
        if self.content_type not in ImageUpload.ALLOWED_CONTENT_TYPES:
            raise ValidationError(f"content_type {self.content_type} not allowed")
        if self.filesize > ImageUpload.MAX_UPLOAD_BYTES:
            raise ValidationError(f"file too large (max {ImageUpload.MAX_UPLOAD_BYTES})")
        
        
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

    async def create_product_image_intent(self,session,product_id) -> ProductImage:
        image = ProductImage(
            product_id=product_id,
            storage_provider="cloudinary",
            mime_type=self.content_type,
            file_size=self.filesize,
            orig_filename=self.orig_filename,
            sort_order=self.sort_order,
            status=ImageUploadStatus.PENDING_UPLOADED,
        )

        session.add(image)
        await session.flush()   
        await session.refresh(image)

        return image



    def build_unq_img_key(self,prod_image_public_id) -> str:
        """
        Deterministic, unguessable storage key suffix
        """
        msg = f"{prod_image_public_id}".encode()
        secret=ImageUpload.FILE_SECRET_KEY
        hash_func = getattr(hashlib, media_settings.HASH_ALGO)
        h = hmac.new(secret.encode(), msg, hash_func).hexdigest()
        # take first 24 hex characters (12 bytes) to keep path shorter but collision-safe
        suffix = h[:24]
        return suffix

    
    async def update_prod_image_storage_key(self,session,prod_image_id,prod_image_pid,uniq_img_key) -> None:
        storage_key=f"{self.FOLDER_PREFIX}/{prod_image_pid}_{uniq_img_key}"
        stmt = (
            update(ProductImage)
            .where(ProductImage.id == prod_image_id)
            .values(storage_key=storage_key)
            .returning(ProductImage.id)
        )

        res = await session.execute(stmt)
        updated = res.scalar_one_or_none()
        if not updated:
            raise RuntimeError(
                "Invariant violated: ProductImage disappeared during init"
            )
        return updated

     
    def build_cloudinary_upload_params(self,prod_image_public_id,unq_img_key:str,expires_in: int = 300):
        timestamp = int(time.time())
        folder=f"{ImageUpload.FOLDER_PREFIX}"
        params_to_sign = {"public_id": f"{prod_image_public_id}_{unq_img_key}", "timestamp": str(timestamp),"unique_filename": "false","overwrite": "false",}
        
        params_to_sign["folder"] = folder

        signature = api_sign_request(params_to_sign, media_settings.CLOUDINARY_API_SECRET)
        response_params = {
            "provider": "cloudinary",
            "upload_url": CLOUDINARY_UPLOAD_URL,
            "params": {
                "api_key": media_settings.CLOUDINARY_API_KEY,
                "timestamp": timestamp,
                "signature": signature,
                "public_id": f"{prod_image_public_id}_{unq_img_key}",
                "folder": folder,
                # optional: tell Cloudinary not to create unique filename (we use deterministic public_id)
                "unique_filename": False,
                "overwrite": False,
            },
            "expires_in": expires_in
        }
        return response_params
    