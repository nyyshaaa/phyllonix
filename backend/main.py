
from contextlib import asynccontextmanager
from fastapi import FastAPI
from backend.api.routers import public_routers,admin_routers
from backend.auth.routes import auth_router
from backend.common.custom_exceptions import register_all_exceptions
from backend.middlewares.auth_middleware import AuthenticationMiddleware
from backend.user.routes import user_router
from backend.db.connection import async_engine,async_session
from backend.__init__ import setup_logger
from backend.api.__init__ import version_prefix,cur_version
from backend.background_workers.base_worker import BasePubSubWorker
from backend.config.admin_config import admin_config


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    setup_logger()
    # base_pubsub=BasePubSubWorker()
    # base_pubsub.start()

    # app.state.pubsub_pub=base_pubsub.publish

    try:
        yield
    finally:
        # at this point new requests accept has been stopped already before calling shutdown
        # await base_pubsub.shutdown()
        # safe to dispose DB engine after workers exit
        await async_engine.dispose()

        
def create_app():
    app=FastAPI(
        title="Phyllonix",
        version=cur_version,
        lifespan=app_lifespan)
    
    app.include_router(public_routers)
     
    if admin_config.ENABLE_ADMIN:
        # extra safety: require an ADMIN_SECRET to be set when enabling in non-dev envs
        if admin_config.ENV == "prod" and not admin_config.ADMIN_SECRET:
            raise RuntimeError("Unsafe configuration: ENABLE_ADMIN=true in PROD requires ADMIN_SECRET")
        app.include_router(admin_routers)      # mounts /api/v1/admin
        #** optional middleware guard (adds header/ip check)
        # app.add_middleware(AdminGuardMiddleware)
    

    app.add_middleware(AuthenticationMiddleware,session=async_session,paths=[f"{version_prefix}/auth"])

    register_all_exceptions(app)
    return app

app=create_app()