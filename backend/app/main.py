"""FastAPI application factory.

Run with: ``uvicorn app.main:create_app --factory --reload``
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.errors import register_api_error_handlers
from app.api.v1.routers import health, players
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.db.session import build_engine, build_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Args:
        settings: Optional explicit settings (used by tests). Defaults to settings
            loaded and validated from the environment.

    Raises:
        ConfigurationError: If required configuration is missing or invalid.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    engine = build_engine(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(
        title="ChessPulse API",
        version=__version__,
        lifespan=lifespan,
        # Interactive docs are a development convenience only.
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.app_env != "production" else None,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = build_session_factory(engine)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    register_api_error_handlers(app)

    # /health is an unversioned operational endpoint; business endpoints use /api/v1.
    app.include_router(health.router)
    app.include_router(players.router)
    return app
