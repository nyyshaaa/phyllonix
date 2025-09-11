from fastapi import APIRouter
from backend.api.__init__ import version_prefix


public_routers = APIRouter(prefix=version_prefix)

auth_router=APIRouter()
user_router=APIRouter()
prods_public_router=APIRouter()

public_routers.include_router(auth_router, prefix="/auth",tags=["auth"])
public_routers.include_router(user_router, prefix="/users",tags=["users"])
public_routers.include_router(prods_public_router, prefix="/products",tags=["products-public"])

#--------------------------------------------------------------------------------------------------------

admin_routers = APIRouter(prefix=f"{version_prefix}/admin")

prods_admin_router=APIRouter()

admin_routers.include_router(prods_admin_router, prefix="/products",tags=["products-admin"])
