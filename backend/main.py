import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from backend.auth.routes import auth_router
from backend.background_workers.specific_workers import LogWorker, NotifyWorker, ThumbnailWorker
from backend.common.constants import NUM_CONSUMERS
from backend.middlewares.auth_middleware import AuthenticationMiddleware
from backend.user.routes import user_router
from backend.db.connection import async_engine,async_session
from backend.__init__ import setup_logger, version_prefix,version

# thumbnail_worker=ThumbnailWorker()

@asynccontextmanager
async def app_lifespan(app: FastAPI):
    setup_logger()
    # constants.tasks_queue = asyncio.Queue()
    # for i in range(NUM_CONSUMERS):
    #     name=f"Worker-{i+1}"
    #     t=asyncio.create_task(thumbnail_worker.thumbnail_worker_loop(constants.tasks_queue,name))
    #     constants.task_workers.append(t)
    # name="main_worker"
    # constants.tasks_executor=asyncio.create_task(thumbnail_worker.thumbnail_worker_loop(constants.tasks_queue,name))
    
    # create exit manager and attach to app.state for access elsewhere / for tests
    # app.state.exit_manager = ExitBgWorkers(
    #     queue=constants.tasks_queue,
    #     worker_loops=constants.task_workers,
    #     num_consumers=NUM_CONSUMERS,
    # )

    # create instances (one instance == one consumer loop)
    thumb = ThumbnailWorker(name="thumb_gen")
    logw = LogWorker(name="log_analytics")
    notif = NotifyWorker(name="notify_admin")

     # attach to app.state for route access / tests
    app.state.thumb_worker = thumb
    app.state.log_worker_sim = logw
    app.state.notif_worker_sim = notif

    # start each worker (runs on this process event loop)
    thumb.start()
    logw.start()
    notif.start()

    try:
        yield
    finally:
        # at this point new requests accept has been stopped already before calling shutdown
        # await app.state.exit_manager.shutdown(drain_first=True)
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