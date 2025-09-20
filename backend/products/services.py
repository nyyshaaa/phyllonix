
import hashlib
import hmac
from fastapi import HTTPException , status
from sqlalchemy import select, text
from backend.products.repository import add_product_categories, validate_catgs
from backend.schema.full_schema import ImageContent, ImageUploadStatus, Product, ProductCategory, ProductImage
from sqlalchemy.exc import IntegrityError
from backend.config.media_config import HASH_ALGO,FILE_SECRET_KEY


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

    def __init__(self,content_type,filesize,filename,checksum):
        self.content_type=content_type
        self.filesize=filesize
        self.orig_filename=filename
        self.checksum=checksum

    def validate_file(self):
        if self.content_type not in ImageUpload.ALLOWED_CONTENT_TYPES:
            raise HTTPException(400, detail=f"content_type {self.content_type} not allowed")
        if self.filesize > ImageUpload.MAX_UPLOAD_BYTES:
            raise HTTPException(413, detail=f"file too large (max {ImageUpload.MAX_UPLOAD_BYTES})")
        
    async def if_image_content_exists(self,session,checksum):
        stmt=select(ImageContent.id,ImageContent.public_id).where(ImageContent.checksum==checksum)
        row=await session.execute(stmt)
        row=row.first()
        if row:
            return {"id":row[0],"public_id":row[1]}
        return None
   
    async def create_image_content(self,session):
        checksum=self.checksum
        insert_sql = text("""
        INSERT INTO imagecontent (checksum, created_at)
        VALUES (:checksum, now())
        ON CONFLICT (checksum) DO NOTHING
        RETURNING id,public_id;
        """)
        res = session.execute(insert_sql, {"checksum": checksum})
        row = res.first()
        if row:
            return {"id":row[0],"public_id":row[1]}
        return None
    
    async def link_image_to_product(self,session,storage_key,image_content_public_id,product_id):
        
        image = ProductImage(
            product_id=product_id,
            public_id=image_content_public_id,
            storage_key=storage_key,
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
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail="Please retry")  # integrity error can happen for same user or different user 



    def storage_key(self,image_content_public_id: str, prefix: str = "images") -> str:
        """
        Deterministic, unguessable storage key
        """
        msg = f"{self.checksum}:{image_content_public_id}".encode()
        secret=ImageUpload.FILE_SECRET_KEY
        hash_func = getattr(hashlib, HASH_ALGO)
        h = hmac.new(secret.encode(), msg, hash_func).hexdigest()
        # take first 24 hex characters (12 bytes) to keep path shorter but collision-safe
        suffix = h[:24]
        return f"{prefix}/{image_content_public_id}/{suffix}"
    
    #* to be implemented
    def generate_presigned_upload(self):
        pass
