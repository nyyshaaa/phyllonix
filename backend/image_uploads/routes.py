from fastapi import APIRouter, Depends, HTTPException, Request , status
from backend.db.dependencies import get_session
from backend.image_uploads.models import InitBatchImagesIn
from backend.image_uploads.services import ImageUpload
from backend.products.repository import product_by_public_id
from sqlalchemy.ext.asyncio import AsyncSession

prod_images_router = APIRouter(tags=["product-images"])

# idempotency not enforced at init level , remove pending rows via background cron processses.
# remove checksum computation(was added to make uploads idempotent) in client side to save from file read and reduce latency for main requests , use a cheap small hint of image data for idempotency or use i key , no idempotency at present for uploads init level .
@prod_images_router.post("/{product_public_id}/images/init-batch")
async def init_images_upload_batch(request:Request,product_public_id: str, imgs_batch: InitBatchImagesIn,session: AsyncSession = Depends(get_session)):
    user_identifier=request.state.user_identifier
    print("init uploads")

    product = await product_by_public_id(session, product_public_id, user_identifier)

    if product.owner_id!=user_identifier:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authorized to update product.")
    
    responses=[]
    errors=[]
    
    for img in imgs_batch.images:
        img_upload=ImageUpload(img.content_type,img.filesize,img.filename,img.sort_order)


        try:
            prod_image = await img_upload.create_prod_image_link(session,product.id)
        except Exception as e:
            #* log actual error
            errors.append( {"filename": img.filename,
                "detail": f"{e} Internal Server Error while creating product image"})
            continue

        print(prod_image)
        print(prod_image.public_id)
         
        uniq_img_key= img_upload.uniq_prod_image_identifier_name(prod_image.public_id)
        print(uniq_img_key)

        if_updated=await img_upload.update_prod_img_storage_key(session,prod_image,uniq_img_key)
        if not if_updated:
            errors.append( {"filename": img.filename,
                    "detail": "Internal Server Error while updating product image"})
            continue

        try:
            upload_params = await img_upload.cloudinary_upload_params(prod_image.public_id,uniq_img_key)

        except Exception as e:
            errors.append( {"filename": img.filename,
                "detail": f"{e}Couldn't generate upload signature , product image pending uploaded "})
            continue

        responses.append({"filename": img.filename,"upload_params":upload_params})
    
    return {"items": responses,"errors":errors}


        







    

    