
from fastapi import APIRouter, Depends

from backend.products.dependency import require_permissions


prods_public_router=APIRouter()
prods_admin_router=APIRouter()

@prods_admin_router.post("/", dependencies=[require_permissions("product:create")])
async def create_product():
    pass