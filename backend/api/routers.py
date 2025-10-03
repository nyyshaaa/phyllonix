from fastapi import APIRouter
from backend.api.__init__ import version_prefix
from backend.auth.routes import auth_router
from backend.user.routes import user_router , user_admin_router
from backend.products.routes import prods_public_router,prods_admin_router
from backend.image_uploads.webhooks import uploads_router
from backend.cart.routes import carts_router



public_routers = APIRouter(prefix=version_prefix)




public_routers.include_router(auth_router, prefix="/auth",tags=["auth"])
public_routers.include_router(user_router, prefix="/users",tags=["users"])
public_routers.include_router(prods_public_router, prefix="/products",tags=["products-public"])
public_routers.include_router(carts_router,prefix="/cart",tags=["cart"])

#--------------------------------------------------------------------------------------------------------

admin_routers = APIRouter(prefix=f"{version_prefix}/admin")

admin_routers.include_router(prods_admin_router, prefix="/products",tags=["products-admin"])
admin_routers.include_router(user_admin_router, prefix="/users",tags=["users-admin"])
admin_routers.include_router(uploads_router, prefix="/uploads",tags=["uploads-admin"])
