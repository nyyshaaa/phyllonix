
import hashlib
import hmac
import time
from fastapi import HTTPException , status
from sqlalchemy import select, text
from backend.products.repository import add_product_categories, validate_catgs
from backend.schema.full_schema import ImageContent, ImageUploadStatus, Product, ProductCategory, ProductImage
from sqlalchemy.exc import IntegrityError
from backend.config.media_config import HASH_ALGO,FILE_SECRET_KEY,CLOUDINARY_API_SECRET,CLOUDINARY_API_KEY,CLOUDINARY_CLOUD_NAME
from cloudinary.utils import api_sign_request

CLOUDINARY_UPLOAD_URL = f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD_NAME}/image/upload"


async def create_product_with_catgs(session,payload,user_id):

    cat_ids=await validate_catgs(session,payload.category_ids)
     
    product = Product(
        name=payload.name,
        description=payload.description,
        base_price=payload.base_price,
        stock_qty=payload.stock_qty,
        sku=payload.sku,
        specs=payload.specs,
        owner_id=user_id
    )

    try:
        session.add(product)
        await session.flush()
         
        await add_product_categories(session,product.id, cat_ids)

        await session.commit()
        await session.refresh(product)
    except IntegrityError:
        await session.rollback()
        res = await session.execute(
            select(Product).where(Product.owner_id == user_id, Product.name == payload.name)
        )
        product = res.scalar_one_or_none()
        if product is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Product with this name already exists")
        await add_product_categories(session,product.id, cat_ids)
        await session.commit()


    return {
        "public_id": str(product.public_id),
        "name": product.name,
        "base_price": product.base_price,
        "stock_qty": product.stock_qty,
        "sku": product.sku,
        "category_ids": cat_ids,
    }

class ImageUpload:
    MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
    ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
    FILE_SECRET_KEY = FILE_SECRET_KEY
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
        
    
    async def link_image_to_product(self,session,img_content,product_id,uniq_img_key):
        
        image = ProductImage(
            product_id=product_id,
            content_id=img_content.id,
            storage_key=f"{ImageUpload.FOLDER_PREFIX}/{img_content.public_id}/{uniq_img_key}",
            storage_provider="cloudinary",
            mime_type=self.content_type,
            file_size=self.filesize,
            checksum=self.checksum,
            status=ImageUploadStatus.PENDING_UPLOADED,
            orig_filename=self.orig_filename
        )
        try:
            session.add(image)
            await session.commit()
            await session.refresh(image)
        except IntegrityError:
            await session.rollback()
            stmt = select(ProductImage).where(ProductImage.storage_key == image.storage_key)
            res = await session.execute(stmt)
            image = res.scalar_one_or_none()
            if image:
                return image
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail="Please retry")  


    def uniq_image_identifier_name(self,image_content_public_id: str) -> str:
        """
        Deterministic, unguessable storage key
        """
        msg = f"{self.checksum}:{image_content_public_id}".encode()
        secret=ImageUpload.FILE_SECRET_KEY
        hash_func = getattr(hashlib, HASH_ALGO)
        h = hmac.new(secret.encode(), msg, hash_func).hexdigest()
        # take first 24 hex characters (12 bytes) to keep path shorter but collision-safe
        suffix = h[:24]
        return suffix
    
    
    def cloudinary_upload_params(image_public_id: str,unq_img_key:str,expires_in: int = 300):
        timestamp = int(time.time())
        params_to_sign = {"unq_img_key": unq_img_key, "timestamp": timestamp}
        folder=f"{ImageUpload.FOLDER_PREFIX}/{image_public_id}"
        params_to_sign["folder"] = folder
        signature = api_sign_request(params_to_sign, CLOUDINARY_API_SECRET)
        response_params = {
            "provider": "cloudinary",
            "upload_url": CLOUDINARY_UPLOAD_URL,
            "params": {
                "api_key": CLOUDINARY_API_KEY,
                "timestamp": timestamp,
                "signature": signature,
                "unq_img_key": unq_img_key,
                "folder": folder,
                # optional: tell Cloudinary not to create unique filename (we use deterministic public_id)
                "unique_filename": False,
                # # optional: prevent accidental overwrite (set to True or False depending on workflow)
                # "overwrite": "true" if overwrite else "false",
            },
            "expires_in": expires_in
        }
        return response_params