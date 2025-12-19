from fastapi import APIRouter, Depends, HTTPException, Request , status
from pydantic import ValidationError
from backend.db.dependencies import get_session
from backend.image_uploads.models import InitBatchImagesIn
from backend.image_uploads.services import ImageUpload
from backend.products.repository import find_product_by_pid
from sqlalchemy.ext.asyncio import AsyncSession
from backend.products.constants import logger

prod_images_router = APIRouter(tags=["product-images"])

@prod_images_router.post("/{product_public_id}/images/init-batch")
async def init_images_upload_batch(request:Request,product_public_id: str, imgs_batch: InitBatchImagesIn,session: AsyncSession = Depends(get_session)):
    user_identifier=request.state.user_identifier
    user_pid = request.state.user_public_id

    product = await find_product_by_pid(session, product_public_id)

    if product["product_owner_id"]!=user_identifier:
        logger.warning("product.image.init.unauthorized",extra={"user": user_pid})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Not authorized to update product.",)
    
    responses: list[dict] = []
    errors: list[dict] = []
    
    for img in imgs_batch.images:
        try:
            img_upload=ImageUpload(img.content_type,img.filesize,img.filename,img.sort_order)
            prod_image = await img_upload.create_product_image_intent(session,product["product_id"])
            
            uniq_img_key= img_upload.build_unq_img_key(prod_image.public_id)

            await img_upload.update_prod_image_storage_key(session,prod_image.id,prod_image.public_id,uniq_img_key)
            upload_params = img_upload.build_cloudinary_upload_params(prod_image.public_id,uniq_img_key)

            responses.append(
                {
                    "image_public_id": str(prod_image.public_id),
                    "filename": img.filename,
                    "upload_params": upload_params,
                }
            )

        except ValidationError as e:
            logger.warning(
                "product.image.init.validation",
                extra={"filename": img.filename},
            )
            errors.append(
                {"filename": img.filename, "detail": str(e)}
            )
            continue

        except Exception:
            raise

    await session.commit()
    return {"items": responses,"errors":errors}


        







    

    