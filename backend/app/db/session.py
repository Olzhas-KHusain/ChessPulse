"""Engine and session factory.

The engine connects lazily: creating the app never opens a database connection, so
``GET /health`` works even when PostgreSQL is down.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


def build_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,  # drop connections that died while idle
        pool_size=5,
        max_overflow=5,
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Sessions for request scope; objects stay readable after commit."""
    return sessionmaker(bind=engine, expire_on_commit=False)
