
from fastapi import APIRouter, Depends, Request

from backend.db.dependencies import get_session
from backend.products.dependency import require_permissions
from backend.products.models import ProductCreateIn
from sqlalchemy.ext.asyncio import AsyncSession

from backend.products.services import create_product_with_catgs


prods_public_router=APIRouter()
prods_admin_router=APIRouter()

@prods_admin_router.post("/", dependencies=[require_permissions("product:create")])
async def create_product(request:Request,payload: ProductCreateIn, session: AsyncSession = Depends(get_session)):
    user_identifier=request.state.user_identifier
    product_res=await create_product_with_catgs(session,payload,user_identifier)
    return product_res

@prods_admin_router.put("/", dependencies=[require_permissions("product:update")])
async def update_product(request:Request,payload: ProductCreateIn, session: AsyncSession = Depends(get_session)):
    user_identifier=request.state.user_identifier
    