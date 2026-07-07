import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.market_data_collector import market_data_collection_loop
from app.core.ml_training_runner import restart_running_ml_training_session
from app.core.startup import run_startup_database_tasks
from app.controllers.exchange_controller import router as exchange_router
from app.controllers.market_data_controller import router as market_data_router
from app.controllers.ml_experiment_controller import router as ml_experiment_router
from app.controllers.ml_training_controller import router as ml_training_router
from app.services.ml_experiment_service import fail_stale_running_experiments


logger = logging.getLogger(__name__)


async def ml_experiment_stale_monitor_loop() -> None:
    while True:
        await asyncio.sleep(60)
        await asyncio.to_thread(fail_stale_running_experiments)


@asynccontextmanager
async def lifespan(app: FastAPI):
    collector_task: asyncio.Task | None = None
    stale_monitor_task: asyncio.Task | None = None
    try:
        logger.info("Running startup database tasks.")
        run_startup_database_tasks()
        logger.info("Startup database tasks completed.")
        failed_stale_count = fail_stale_running_experiments()
        if failed_stale_count:
            logger.warning("Failed %s stale ML experiment(s) during startup.", failed_stale_count)
        stale_monitor_task = asyncio.create_task(ml_experiment_stale_monitor_loop())
        if get_settings().market_data_auto_collect:
            collector_task = asyncio.create_task(market_data_collection_loop())
        else:
            logger.info("Market data auto-collector is disabled.")
        await restart_running_ml_training_session()
    except Exception:
        logger.exception("Startup database tasks failed.")
        raise
    try:
        yield
    finally:
        if stale_monitor_task:
            stale_monitor_task.cancel()
            try:
                await stale_monitor_task
            except asyncio.CancelledError:
                pass
        if collector_task:
            collector_task.cancel()
            try:
                await collector_task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="FuturesML", version="0.1.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(exchange_router)
app.include_router(market_data_router)
app.include_router(ml_training_router)
app.include_router(ml_experiment_router)


@app.get("/")
def root_redirect():
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/exchanges", status_code=303)
