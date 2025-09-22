
from fastapi import APIRouter, Depends, HTTPException, Request,status

from backend.db.dependencies import get_session
from backend.products.dependency import require_permissions
from backend.products.models import ProductCreateIn, ProductUpdateIn
from sqlalchemy.ext.asyncio import AsyncSession

from backend.products.repository import patch_product, product_by_public_id, replace_catgs, validate_catgs
from backend.products.services import create_product_with_catgs


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

