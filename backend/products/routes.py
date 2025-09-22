
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

        img_content=await img_upload.if_image_content_exists(session,img.checksum,user_identifier)

        if img_content and img_content.owner_id!=user_identifier:
            errors.append({
                    "filename": img.filename,
                    "detail": "Image belongs to another user",
            })
            continue

        if not img_content:
            try:
                img_content=await img_upload.create_image_content(session,user_identifier)
            except Exception as e:
                errors.append( {"filename": img.filename,
                    "detail": "Internal Server Error , Retry "})
                continue

        uniq_img_key= img_upload.uniq_image_identifier_name(img_content.public_id)

        try:
            await img_upload.link_image_to_product(session,img_content,product.id,uniq_img_key)
        except Exception:
            errors.append( {"filename": img.filename,
                "detail": "Internal Server Error , Retry "})
            continue
      
        upload_params = img_upload.cloudinary_upload_params(img_content.public_id,uniq_img_key)

        if not upload_params:
            errors.append( {"filename": img.filename,
                "detail": "Couldn't generate upload signature , image added and linked , please retry "})
            continue

        responses.append(upload_params)
    
    return {"items": responses,"errors":errors}


        







    

    