import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from backend.auth.routes import auth_router
from backend.common.constants import NUM_CONSUMERS
from backend.middlewares.auth_middleware import AuthenticationMiddleware
from backend.user.routes import user_router
from backend.db.connection import async_engine,async_session
from backend.__init__ import version_prefix,version
from backend.user import constants
from backend.background_workers.thumbnail_worker import ThumbnailWorker
from backend.background_workers.stop_workers import ExitBgWorkers

thumbnail_worker=ThumbnailWorker()

@asynccontextmanager
async def app_lifespan(app: FastAPI):
    constants.tasks_queue = asyncio.Queue()
    constants.tasks_executor = asyncio.create_task(thumbnail_worker.thumbnail_worker_loop(constants.tasks_queue))
    # create exit manager and attach to app.state for access elsewhere / for tests
    app.state.exit_manager = ExitBgWorkers(
        queue=constants.tasks_queue,
        worker_loop=constants.tasks_executor,
        num_consumers=NUM_CONSUMERS,
    )
    try:
        yield
    finally:
        # at this point new requests accept has been stopped already before calling shutdown
        await app.state.exit_manager.shutdown(drain_first=True)
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