"""FastAPI application factory with lifespan management."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings

log = structlog.get_logger(__name__)


def _configure_logging() -> None:
    import logging

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialise resources on startup and tear down on shutdown."""
    _configure_logging()

    weak = settings.weak_secrets()
    if weak and settings.APP_ENV not in ("development", "test"):
        raise RuntimeError(
            f"Refusing to start with APP_ENV={settings.APP_ENV}: {', '.join(weak)} "
            "is empty, a placeholder or shorter than 32 characters. "
            "Generate one with: openssl rand -hex 32 "
            "(changing ENCRYPTION_KEY makes stored connection credentials unreadable)"
        )
    if weak:
        log.warning("app.weak_secrets", settings=weak, note="only acceptable in development and test")
    log.info("app.started", env=settings.APP_ENV)

    if settings.ARKITEKTEN_URL:
        # Före schemaläggaren, så att ett nyskapat schema laddas med de andra.
        from app.database import async_session
        from app.services.arkitekten_kalla import se_till_att_källan_finns
        try:
            async with async_session() as db:
                await se_till_att_källan_finns(db, settings.ARKITEKTEN_URL)
        except Exception as e:  # en källa som saknas får inte stoppa plattformen
            log.error("arkitekten.kalla_misslyckades", error=str(e))

    from app.tasks.scheduler import start_scheduler, shutdown_scheduler
    await start_scheduler()

    yield

    await shutdown_scheduler()
    log.info("app.stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Integration Platform API",
        description="General-purpose integration platform — fetch, transform, store, and serve data from external systems",
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # Rate limiting (inside CORS, so a 429 still carries the CORS headers)
    from app.ratelimit import limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from app.api.router import api_router
    app.include_router(api_router)

    return app


app = create_app()
