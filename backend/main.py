from contextlib import asynccontextmanager
from fastapi import FastAPI,APIRouter
from backend.auth.routes import auth_router
from backend.db import async_engine
from backend.__init__ import version_prefix


@asynccontextmanager
async def app_lifespan(app: FastAPI):

    yield
    
    async_engine.dispose()

def create_app():
    app=FastAPI(lifespan=app_lifespan)
    app.include_router(auth_router, prefix=version_prefix)
    return app

app=create_app()