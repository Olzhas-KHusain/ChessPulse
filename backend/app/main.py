"""FastAPI application factory.

Run with: ``uvicorn app.main:create_app --factory --reload``
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.v1.errors import register_api_error_handlers
from app.api.v1.routers import board, health, players
from app.core.config import ConfigurationError, Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.db.session import build_engine, build_session_factory
from app.engine.runtime import stockfish_factory
from app.services.board import BoardAnalysisService


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
        try:
            yield
        finally:
            app.state.board_service.close()
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
    app.state.board_service = BoardAnalysisService(stockfish_factory(settings))

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
    app.include_router(board.router)

    _static = Path(settings.static_dir).resolve() if settings.static_dir else None
    if _static is not None:
        if not (_static / "index.html").is_file():
            raise ConfigurationError(f"static_dir has no index.html: {_static}")
        # Hashed build assets are immutable; everything else falls back to
        # index.html so client-side routing works on reload/direct entry.
        app.mount("/assets", StaticFiles(directory=_static / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str) -> FileResponse:  # pragma: no cover - serving only
            if full_path.startswith(("api/", "health")):
                raise HTTPException(status_code=404)
            candidate = _static / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(_static / "index.html")

    return app
