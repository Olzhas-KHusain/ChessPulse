"""Request-scoped dependencies. Tests override these with ``app.dependency_overrides``."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from app.analytics.window import WINDOW_DAYS
from app.core.config import Settings
from app.providers.base import GameDataProvider
from app.providers.chess_com import ChessComProvider
from app.services.board import BoardAnalysisService
from app.services.scope import PERIOD_OPTIONS, TIME_CLASS_OPTIONS, Scope, parse_scope


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_session(request: Request) -> Iterator[Session]:
    session: Session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_provider(request: Request) -> Iterator[GameDataProvider]:
    provider = ChessComProvider.from_settings(request.app.state.settings)
    try:
        yield provider
    finally:
        provider.close()


def get_now() -> datetime:
    return datetime.now(UTC)


def get_board_service(request: Request) -> BoardAnalysisService:
    service: BoardAnalysisService = request.app.state.board_service
    return service


def get_scope(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    time_class: Annotated[
        str,
        Query(description=f"Time class: {', '.join(TIME_CLASS_OPTIONS)}."),
    ] = "rapid",
    days: Annotated[
        int,
        Query(description=f"Period length in days: {', '.join(map(str, PERIOD_OPTIONS))}."),
    ] = WINDOW_DAYS,
) -> Scope:
    """Validated ``(time_class, days)`` pair shared by every player endpoint."""
    return parse_scope(settings, time_class, days)
