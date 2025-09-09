import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from backend.auth.routes import auth_router
from backend.common.constants import NUM_CONSUMERS
from backend.middlewares.auth_middleware import AuthenticationMiddleware
from backend.user.routes import user_router
from backend.db.connection import async_engine,async_session
from backend.__init__ import setup_logger, version_prefix,version
from backend.background_workers.base_worker import BaseWorker



@asynccontextmanager
async def app_lifespan(app: FastAPI):
    setup_logger()
    base_worker=BaseWorker()
    await base_worker()

    app.state.queue=base_worker.queue
   
    try:
        yield
    finally:
        # at this point new requests accept has been stopped already before calling shutdown
        await base_worker.shutdown()
        # safe to dispose DB engine after workers exit
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