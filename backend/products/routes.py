
from fastapi import APIRouter, Depends

from backend.db.dependencies import get_session
from backend.products.dependency import require_permissions
from backend.products.models import ProductCreateIn
from sqlalchemy.ext.asyncio import AsyncSession


prods_public_router=APIRouter()
prods_admin_router=APIRouter()

@prods_admin_router.post("/", dependencies=[require_permissions("product:create")])
async def create_product(payload: ProductCreateIn, session: AsyncSession = Depends(get_session)):
    pass