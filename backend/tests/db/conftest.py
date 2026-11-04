"""PostgreSQL fixtures for database tests.

Each test session creates its own temporary database on the configured server,
migrates it with Alembic (so triggers and hand-written DDL are exercised), and drops
it afterwards. Development data is never touched.

Server selection: ``TEST_DATABASE_URL`` if set, otherwise ``DATABASE_URL`` from the
application settings. If neither is configured or the server is unreachable, every
test in this package is skipped. The role needs the CREATEDB privilege (the Docker
Compose superuser has it).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import URL, Engine, create_engine, make_url, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_now, get_provider
from app.core.config import ConfigurationError, Settings, load_settings
from app.main import create_app
from tests.ingestion_helpers import NOW

BACKEND_DIR = Path(__file__).resolve().parents[2]
APP_TABLES = (
    "analysis_jobs",
    "game_analysis",
    "cache_metadata",
    "player_games",
    "games",
    "openings",
    "players",
)


def _server_url() -> URL | None:
    raw = os.environ.get("TEST_DATABASE_URL")
    if not raw:
        try:
            raw = load_settings().database_url.get_secret_value()
        except ConfigurationError:
            return None
    return make_url(raw)


def _admin_engine(server_url: URL) -> Engine:
    return create_engine(
        server_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 3},
    )


def alembic_config() -> Config:
    """Alembic config that never reads ``DATABASE_URL`` (a connection is supplied)."""
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["skip_logging_config"] = True
    return cfg


def run_alembic(engine: Engine, action: str, revision: str) -> None:
    """Run ``alembic upgrade|downgrade <revision>`` on ``engine``'s database."""
    cfg = alembic_config()
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        getattr(command, action)(cfg, revision)


class TemporaryDatabases:
    """Creates and drops uniquely named databases on one server."""

    def __init__(self, server_url: URL) -> None:
        self._server_url = server_url
        self._admin = _admin_engine(server_url)
        self._created: list[str] = []

    def create(self) -> Engine:
        name = f"chesspulse_test_{uuid.uuid4().hex[:12]}"
        with self._admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
        self._created.append(name)
        return create_engine(self._server_url.set(database=name))

    def drop_all(self) -> None:
        with self._admin.connect() as conn:
            for name in self._created:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        self._admin.dispose()


@pytest.fixture(scope="session")
def temp_databases() -> Iterator[TemporaryDatabases]:
    server_url = _server_url()
    if server_url is None:
        pytest.skip("No TEST_DATABASE_URL or DATABASE_URL configured")
    try:
        with _admin_engine(server_url).connect():
            pass
    except OperationalError:
        pytest.skip("PostgreSQL is not reachable (start it with: docker compose up -d db)")
    databases = TemporaryDatabases(server_url)
    try:
        yield databases
    finally:
        databases.drop_all()


@pytest.fixture(scope="session")
def migrated_engine(temp_databases: TemporaryDatabases) -> Iterator[Engine]:
    """A database migrated to ``head``, shared by the whole session."""
    engine = temp_databases.create()
    run_alembic(engine, "upgrade", "head")
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def empty_engine(temp_databases: TemporaryDatabases) -> Iterator[Engine]:
    """A brand-new empty database (for migration tests)."""
    engine = temp_databases.create()
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session(migrated_engine: Engine) -> Iterator[Session]:
    """A session on the migrated database; all rows are removed after the test.

    Tests commit for real, because the participant/result triggers are deferred
    to COMMIT and would never fire inside a rolled-back outer transaction.
    """
    with Session(migrated_engine, expire_on_commit=False) as db_session:
        yield db_session
        db_session.rollback()
    with migrated_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(APP_TABLES)} RESTART IDENTITY CASCADE"))


Client = Callable[..., TestClient]


@pytest.fixture
def client(session: Session, migrated_engine: Engine) -> Iterator[Client]:
    """Builds a TestClient for a given provider and clock; ``session`` truncates after."""
    created: list[TestClient] = []

    def build(provider: object, now: datetime | None = None) -> TestClient:
        settings = Settings(
            _env_file=None,
            database_url=migrated_engine.url.render_as_string(hide_password=False),
        )
        app = create_app(settings)
        app.dependency_overrides[get_provider] = lambda: provider
        app.dependency_overrides[get_now] = lambda: now or NOW
        test_client = TestClient(app)
        created.append(test_client)
        return test_client

    yield build
    for test_client in created:
        test_client.close()
