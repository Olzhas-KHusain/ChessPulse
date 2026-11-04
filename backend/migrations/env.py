"""Alembic environment.

Connection sources, in priority order:

1. ``config.attributes["connection"]``: an open SQLAlchemy connection supplied by
   the caller (used by the test suite to migrate a temporary database).
2. ``DATABASE_URL`` from the validated application settings.

The URL is never read from ``alembic.ini`` and is never printed.
"""

from __future__ import annotations

from logging.config import fileConfig
from typing import Any

from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy import Connection, create_engine, pool

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.db.base import Base
from app.db.types import UtcDateTime

config = context.config

if config.config_file_name is not None and not config.attributes.get("skip_logging_config"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def render_item(type_: str, obj: Any, autogen_context: AutogenContext) -> str | bool:
    """Render project-specific types as plain SQLAlchemy types in migration files.

    Migrations must not import application code that may change later, so
    ``UtcDateTime`` is written as the column type it actually creates.
    """
    if type_ == "type" and isinstance(obj, UtcDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def _configure_options() -> dict[str, Any]:
    return {
        "target_metadata": target_metadata,
        "compare_type": True,
        "render_item": render_item,
    }


def run_migrations_offline() -> None:
    """Emit SQL to stdout (``alembic upgrade head --sql``) without connecting."""
    from app.core.config import get_settings

    context.configure(
        url=get_settings().database_url.get_secret_value(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_configure_options(),
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_with_connection(connection: Connection) -> None:
    context.configure(connection=connection, **_configure_options())
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    supplied = config.attributes.get("connection")
    if supplied is not None:
        _run_with_connection(supplied)
        return

    from app.core.config import get_settings

    engine = create_engine(get_settings().database_url.get_secret_value(), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            _run_with_connection(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
