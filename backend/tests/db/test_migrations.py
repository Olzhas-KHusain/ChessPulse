"""Migration application, downgrade, and model/migration drift."""

from __future__ import annotations

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text

from app.db.base import Base
from tests.db.conftest import APP_TABLES, alembic_config, run_alembic

pytestmark = pytest.mark.integration

EXPECTED_INDEXES = {
    "games": {
        "ix_games_played_at",
        "ix_games_time_class_played_at",
        "ix_games_white_player_id",
        "ix_games_black_player_id",
        "ix_games_opening_id",
        "uq_games_provider_provider_game_id",
    },
    "players": {"uq_players_provider_username", "uq_players_provider_provider_player_id"},
    "player_games": {"uq_player_games_player_id_game_id", "uq_player_games_game_id_color"},
    "openings": {"ix_openings_eco_code", "uq_openings_source_source_opening_id"},
    "cache_metadata": {
        "ix_cache_metadata_expires_at",
        "ix_cache_metadata_player_id",
        "uq_cache_metadata_cache_key",
    },
}


def _head() -> str:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    assert head is not None
    return head


def _index_names(engine: Engine, table: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = :t"),
            {"t": table},
        )
        return {row[0] for row in rows}


def test_upgrade_applies_to_an_empty_database(empty_engine: Engine) -> None:
    run_alembic(empty_engine, "upgrade", "head")

    tables = set(inspect(empty_engine).get_table_names())
    assert tables == {*APP_TABLES, "alembic_version"}
    with empty_engine.connect() as conn:
        version: str = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == _head()


def test_expected_indexes_exist(migrated_engine: Engine) -> None:
    for table, expected in EXPECTED_INDEXES.items():
        assert expected <= _index_names(migrated_engine, table), table


def test_consistency_triggers_exist(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tgname, tgdeferrable, tginitdeferred FROM pg_trigger "
                "WHERE NOT tgisinternal ORDER BY tgname"
            )
        ).all()
    assert [tuple(row) for row in rows] == [
        ("trg_games_consistency", True, True),
        ("trg_player_games_consistency", True, True),
    ]


def test_timestamp_columns_are_timezone_aware(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name, column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'public' AND data_type LIKE 'timestamp%'"
            )
        ).all()
    assert rows, "expected timestamp columns"
    assert {row.data_type for row in rows} == {"timestamp with time zone"}


def test_models_match_migrations(migrated_engine: Engine) -> None:
    """Fails when a model changes without a matching migration."""
    with migrated_engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(context, Base.metadata)
    assert diff == []


def test_downgrade_to_base_removes_everything_and_upgrade_again(empty_engine: Engine) -> None:
    run_alembic(empty_engine, "upgrade", "head")
    run_alembic(empty_engine, "downgrade", "base")

    assert set(inspect(empty_engine).get_table_names()) == {"alembic_version"}
    with empty_engine.connect() as conn:
        functions: int = conn.execute(
            text(
                "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'public'"
            )
        ).scalar_one()
    assert functions == 0

    run_alembic(empty_engine, "upgrade", "head")
    assert set(inspect(empty_engine).get_table_names()) == {*APP_TABLES, "alembic_version"}
