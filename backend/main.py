
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from backend.api.routers import public_routers,admin_routers
from backend.auth.routes import auth_router
from backend.common.custom_exceptions import register_all_exceptions
from backend.common.logging_setup import setup_logging
from backend.db.dependencies import get_session
from backend.middlewares.auth_middleware import AuthenticationMiddleware
from backend.middlewares.device_authentication_middleware import DeviceSessionMiddleware
from backend.middlewares.rate_limit_middleware import RateLimitMiddleware
from backend.middlewares.request_id_middleware import RequestIdMiddleware
from backend.orders.webhooks import razorpay_webhook
from backend.user.routes import user_router
from backend.db.connection import async_engine,async_session
from backend.api.__init__ import version_prefix,cur_version
from backend.background_workers.base_pubsub_interface import BasePubSubWorker
from backend.config.admin_config import admin_config
from metrics.custom_instrumentator import instrumentator
from backend.config.settings import config_settings

rzpay_webhook_path = config_settings.RZPAY_WEBHOOK_PATH

@asynccontextmanager
async def app_lifespan(app: FastAPI):
    setup_logging()
    app.state.rate_limit_strategy = "fixed_window"
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

    app.add_api_route(rzpay_webhook_path,razorpay_webhook,methods=["POST"],name="razorpay_webhook",dependencies=[Depends(get_session)] 
    )
     
    if admin_config.ENABLE_ADMIN:
        # extra safety: require an ADMIN_SECRET to be set when enabling in non-dev envs
        # if admin_config.ENV == "prod" and not admin_config.ADMIN_SECRET:
        #     raise RuntimeError("Unsafe configuration: ENABLE_ADMIN=true in PROD requires ADMIN_SECRET")
        app.include_router(admin_routers)      # mounts /api/v1/admin
        #** optional middleware guard (adds header/ip check)
        # app.add_middleware(AdminGuardMiddleware)
    
    # app.add_middleware(DeviceSessionMiddleware,session=async_session,paths=[f"{version_prefix}/cart/items",
    #                                                                         f"{version_prefix}/checkout"])
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuthenticationMiddleware,session=async_session,paths=[f"{version_prefix}/auth/",
                                                                             f"{version_prefix}/health",
                                                                             f"{version_prefix}/session/init",
                                                                             f"{version_prefix}/admin/uploads",f"{version_prefix}/webhooks",
                                                                             f"webhooks",
                                                                             f"{version_prefix}/products",                         # for non admin public product routes 
                                                                             f"{version_prefix}/orders/test/checkout"],
                                                                             maybe_auth_paths=[f"{version_prefix}/cart/items"])
    app.add_middleware(RequestIdMiddleware)
    register_all_exceptions(app)
    # instrumentator.instrument(app).expose(app, endpoint="/metrics")
    
    return app

app=create_app()