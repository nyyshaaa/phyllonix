
import hashlib
import hmac
import time
from fastapi import HTTPException , status
from sqlalchemy import select, text, update
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
        
    
    async def create_prod_image_link(self,session,product_id,user_id):
        
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
        # except IntegrityError:
        #     await session.rollback()
        #     stmt = select(ProductImage).where(
        #         ProductImage.product_id == product_id,
        #         ProductImage.owner_id == user_id,
        #         ProductImage.orig_filename == self.orig_filename,
        #         ProductImage.file_size == self.filesize
        #     )
        #     res = await session.execute(stmt)
        #     prod_image = res.scalar_one_or_none()
        #     if prod_image:
        #         return prod_image
        #     raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail="Please retry")


    def uniq_prod_image_identifier_name(self,prod_image_public_id: str) -> str:
        """
        Deterministic, unguessable storage key
        """
        msg = f"{prod_image_public_id}".encode()
        secret=ImageUpload.FILE_SECRET_KEY
        hash_func = getattr(hashlib, HASH_ALGO)
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
            )
            await session.execute(stmt)
            await session.commit()

    
    async def cloudinary_upload_params(prod_image_public_id: str,unq_img_key:str,expires_in: int = 300):
        timestamp = int(time.time())
        params_to_sign = {"public_id": unq_img_key, "timestamp": timestamp}
        folder=f"{ImageUpload.FOLDER_PREFIX}/{prod_image_public_id}"
        params_to_sign["folder"] = folder
        signature = api_sign_request(params_to_sign, CLOUDINARY_API_SECRET)
        response_params = {
            "provider": "cloudinary",
            "upload_url": CLOUDINARY_UPLOAD_URL,
            "params": {
                "api_key": CLOUDINARY_API_KEY,
                "timestamp": timestamp,
                "signature": signature,
                "public_id": unq_img_key,
                "folder": folder,
                # optional: tell Cloudinary not to create unique filename (we use deterministic public_id)
                "unique_filename": False,
                # # optional: prevent accidental overwrite (set to True or False depending on workflow)
                # "overwrite": "true" if overwrite else "false",
            },
            "expires_in": expires_in
        }
        return response_params