from contextlib import asynccontextmanager
from fastapi import FastAPI,APIRouter
from backend.auth.routes import auth_router
from backend.middlewares.auth_middleware import AuthenticationMiddleware
from backend.user.routes import user_router
from backend.db.connection import async_engine,async_session
from backend.__init__ import version_prefix,version


@asynccontextmanager
async def app_lifespan(app: FastAPI):

    yield
    
    await async_engine.dispose() 

def create_app():
    app=FastAPI(
        title="Phyllonix",
        version=version,
        lifespan=app_lifespan)
    app.include_router(auth_router, prefix=f"{version_prefix}/auth")
    app.include_router(user_router,prefix=f"{version_prefix}/users")

    app.add_middleware(AuthenticationMiddleware,session=async_session,paths=[f"{version_prefix}/auth"])
    return app

app=create_app()