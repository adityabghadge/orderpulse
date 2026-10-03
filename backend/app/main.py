import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes import health
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.db.session import SessionLocal
from app.services.stats import refresh_daily_operations

log = logging.getLogger("orderpulse")


def _refresh_stats() -> None:
    with SessionLocal() as db:
        if refresh_daily_operations(db):
            log.info("Refreshed daily operations totals")


async def _refresh_stats_forever(interval_seconds: int) -> None:
    """Keep the precomputed daily totals fresh while the API runs."""
    while True:
        try:
            await run_in_threadpool(_refresh_stats)
        except Exception:  # keep the loop alive; the next run may succeed
            log.exception("Refreshing daily operations totals failed")
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    task = None
    if settings.background_jobs:
        task = asyncio.create_task(_refresh_stats_forever(settings.stats_refresh_seconds))
    yield
    if task:
        task.cancel()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Operations API for orders, returns and refunds.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Response-Time-Ms", "Idempotent-Replayed", "X-Cache"],
    )

    @app.middleware("http")
    async def add_response_time(request: Request, call_next):
        # Every response reports how long the server spent on it, so latency
        # improvements (caching, query tuning) can be measured, not guessed.
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Response-Time-Ms"] = f"{(time.perf_counter() - start) * 1000:.1f}"
        return response

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(api_router)
    return app


app = create_app()
