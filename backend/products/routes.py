
from fastapi import APIRouter, Depends, HTTPException, Request,status

from backend.db.dependencies import get_session
from backend.products.dependency import require_permissions
from backend.products.models import InitBatchImagesIn, ProductCreateIn, ProductUpdateIn
from sqlalchemy.ext.asyncio import AsyncSession

from backend.products.repository import patch_product, product_by_public_id, replace_catgs, validate_catgs
from backend.products.services import ImageUpload, create_product_with_catgs


prods_public_router=APIRouter()
prods_admin_router=APIRouter()

@prods_admin_router.post("/", dependencies=[require_permissions("product:create")])
async def create_product(request:Request,payload: ProductCreateIn, session: AsyncSession = Depends(get_session)):
    print("create prods")
    user_identifier=request.state.user_identifier
    print(user_identifier)
    product_res=await create_product_with_catgs(session,payload,user_identifier)
    return {"message":"product created","product":product_res}

@prods_admin_router.patch("/{product_public_id}", dependencies=[require_permissions("product:update")])
async def update_product(request:Request,product_public_id: str,
                         payload: ProductUpdateIn, session: AsyncSession = Depends(get_session)):
                         
    cat_ids=await validate_catgs(session,payload.category_ids)
    user_identifier=request.state.user_identifier

    product = await product_by_public_id(session, product_public_id, user_identifier)

    if product.owner_id!=user_identifier:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authorized to update.")

    updates = payload.model_dump(exclude_unset=True)
    updates.pop("category_ids")

    product_id = await patch_product(session, updates, user_identifier,product.id)

    await replace_catgs(session,product_id,cat_ids)

    return {"message":"product updated"}

# idempotency not enforced at init level , don't give users and option to retry in case of network failures , remove pending rows via background cron processses.
# avoid checksum computation in client side to save from file read and reduce latency for main requests , use a cheap small hint of image data for idempotency or use i key , no idempotency at present for uploads init level .
@prods_admin_router.post("/{product_public_id}/images/init-batch")
async def init_images_upload_batch(request:Request,product_public_id: str, imgs_batch: InitBatchImagesIn,session: AsyncSession = Depends(get_session)):
    user_identifier=request.state.user_identifier

    product = await product_by_public_id(session, product_public_id, user_identifier)

    if product.owner_id!=user_identifier:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authorized to update.")
    
    responses=[]
    errors=[]
    
    for img in imgs_batch.images:
        img_upload=ImageUpload(img.content_type,img.filesize,img.filename,img.checksum)


        try:
            prod_image = await img_upload.create_prod_image_link(session,product.id)
        except Exception:
            errors.append( {"filename": img.filename,
                "detail": "Internal Server Error while creating product image"})
            continue
         
        uniq_img_key= img_upload.uniq_prod_image_identifier_name(prod_image.public_id)

        if_updated=await img_upload.update_prod_img_storage_key(session,prod_image,uniq_img_key)
        if not if_updated:
            errors.append( {"filename": img.filename,
                    "detail": "Internal Server Error while updating product image"})
            continue

        try:
            upload_params = await img_upload.cloudinary_upload_params(prod_image.public_id,uniq_img_key)

        except Exception:
            errors.append( {"filename": img.filename,
                "detail": "Couldn't generate upload signature , product image pending uploaded "})
            continue

        responses.append({"filename": img.filename,"upload_params":upload_params})
    
    return {"items": responses,"errors":errors}


        







    

    