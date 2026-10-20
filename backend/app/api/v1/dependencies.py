"""Request-scoped dependencies. Tests override these with ``app.dependency_overrides``."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.providers.base import GameDataProvider
from app.providers.chess_com import ChessComProvider


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
