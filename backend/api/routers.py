from fastapi import APIRouter
from backend.api.__init__ import version_prefix
from backend.auth.routes import auth_router
from backend.user.routes import user_router
from backend.products.routes import prods_public_router,prods_admin_router



public_routers = APIRouter(prefix=version_prefix)




public_routers.include_router(auth_router, prefix="/auth",tags=["auth"])
public_routers.include_router(user_router, prefix="/users",tags=["users"])
public_routers.include_router(prods_public_router, prefix="/products",tags=["products-public"])

#--------------------------------------------------------------------------------------------------------

admin_routers = APIRouter(prefix=f"{version_prefix}/admin")

admin_routers.include_router(prods_admin_router, prefix="/products",tags=["products-admin"])
