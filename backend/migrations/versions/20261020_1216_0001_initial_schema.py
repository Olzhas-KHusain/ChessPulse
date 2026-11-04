"""Initial schema: players, openings, games, player_games, cache_metadata.

Revision ID: 0001
Revises:
Create Date: 2026-10-20 12:16:07

Generated with ``alembic revision --autogenerate`` and then edited by hand:

* Enum columns are plain VARCHAR with exactly one named CHECK constraint each.
  Autogenerate emitted every enum CHECK twice (and ``sa.Enum(create_constraint=True)``
  would have added a third), which fails with duplicate constraint names.
* Deferred constraint triggers keep ``player_games.color`` / ``player_games.result``
  consistent with ``games``. Autogenerate cannot detect triggers, so they live only
  here; ``tests/db/test_migrations.py`` asserts that they exist.

Design decisions: docs/specs/database-schema.md.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[Any]]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def _id() -> sa.Column[Any]:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False)


PLAYER_GAME_CONSISTENCY_SQL = """
CREATE FUNCTION player_games_validate(p_player_game_id bigint) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    pg player_games%ROWTYPE;
    g games%ROWTYPE;
    expected_result varchar;
BEGIN
    -- Validate the row as it exists at commit time; it may have been changed or
    -- deleted later in the same transaction.
    SELECT * INTO pg FROM player_games WHERE id = p_player_game_id;
    IF NOT FOUND THEN
        RETURN;
    END IF;
    SELECT * INTO g FROM games WHERE id = pg.game_id;
    IF NOT FOUND THEN
        RETURN;  -- the FK (ON DELETE CASCADE) removes the association with the game
    END IF;

    IF (pg.color = 'white' AND pg.player_id <> g.white_player_id)
       OR (pg.color = 'black' AND pg.player_id <> g.black_player_id) THEN
        RAISE EXCEPTION 'player_games % does not match the % participant of game %',
            pg.id, pg.color, g.id
            USING ERRCODE = 'check_violation',
                  CONSTRAINT = 'ck_player_games_participant',
                  TABLE = 'player_games';
    END IF;

    expected_result := CASE
        WHEN g.result = 'draw' THEN 'draw'
        WHEN g.result = 'unknown' THEN 'unknown'
        WHEN g.result = 'white_win' AND pg.color = 'white' THEN 'win'
        WHEN g.result = 'black_win' AND pg.color = 'black' THEN 'win'
        ELSE 'loss'
    END;
    IF pg.result <> expected_result THEN
        RAISE EXCEPTION 'player_games % result does not match the result of game %',
            pg.id, g.id
            USING ERRCODE = 'check_violation',
                  CONSTRAINT = 'ck_player_games_result_matches_game',
                  TABLE = 'player_games';
    END IF;
END;
$$;

CREATE FUNCTION player_games_consistency_trigger() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM player_games_validate(NEW.id);
    RETURN NULL;
END;
$$;

CREATE FUNCTION games_consistency_trigger() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    pg_id bigint;
BEGIN
    FOR pg_id IN SELECT id FROM player_games WHERE game_id = NEW.id LOOP
        PERFORM player_games_validate(pg_id);
    END LOOP;
    RETURN NULL;
END;
$$;

-- Deferred to COMMIT so that a correction may update a game and its
-- player_games rows in any order inside one transaction.
CREATE CONSTRAINT TRIGGER trg_player_games_consistency
    AFTER INSERT OR UPDATE OF player_id, game_id, color, result ON player_games
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION player_games_consistency_trigger();

CREATE CONSTRAINT TRIGGER trg_games_consistency
    AFTER UPDATE OF white_player_id, black_player_id, result ON games
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW
    WHEN (
        OLD.white_player_id IS DISTINCT FROM NEW.white_player_id
        OR OLD.black_player_id IS DISTINCT FROM NEW.black_player_id
        OR OLD.result IS DISTINCT FROM NEW.result
    )
    EXECUTE FUNCTION games_consistency_trigger();
"""


def upgrade() -> None:
    op.create_table(
        "players",
        _id(),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_player_id", sa.String(length=64), nullable=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("profile_url", sa.Text(), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("current_rapid_rating", sa.Integer(), nullable=True),
        sa.Column("current_rapid_rating_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("provider IN ('chess_com')", name=op.f("ck_players_provider")),
        sa.CheckConstraint(
            "username = lower(username)", name=op.f("ck_players_username_lowercase")
        ),
        sa.CheckConstraint("char_length(username) > 0", name=op.f("ck_players_username_not_empty")),
        sa.CheckConstraint(
            "current_rapid_rating IS NULL OR current_rapid_rating >= 0",
            name=op.f("ck_players_current_rapid_rating_non_negative"),
        ),
        sa.CheckConstraint(
            "current_rapid_rating_at IS NULL OR current_rapid_rating IS NOT NULL",
            name=op.f("ck_players_current_rapid_rating_at_requires_rating"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_players")),
        sa.UniqueConstraint(
            "provider", "provider_player_id", name=op.f("uq_players_provider_provider_player_id")
        ),
        sa.UniqueConstraint("provider", "username", name=op.f("uq_players_provider_username")),
    )

    op.create_table(
        "openings",
        _id(),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_opening_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("eco_code", sa.String(length=3), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("source IN ('chess_com')", name=op.f("ck_openings_opening_source")),
        sa.CheckConstraint(
            "char_length(source_opening_id) > 0",
            name=op.f("ck_openings_source_opening_id_not_empty"),
        ),
        sa.CheckConstraint("char_length(name) > 0", name=op.f("ck_openings_name_not_empty")),
        sa.CheckConstraint(
            "eco_code IS NULL OR eco_code ~ '^[A-E][0-9]{2}$'",
            name=op.f("ck_openings_eco_code_format"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_openings")),
        sa.UniqueConstraint(
            "source", "source_opening_id", name=op.f("uq_openings_source_source_opening_id")
        ),
    )
    op.create_index(op.f("ix_openings_eco_code"), "openings", ["eco_code"])

    op.create_table(
        "games",
        _id(),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_game_id", sa.String(length=128), nullable=False),
        sa.Column("game_url", sa.Text(), nullable=True),
        sa.Column("played_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_class", sa.String(length=16), nullable=False),
        sa.Column("time_control", sa.String(length=32), nullable=True),
        sa.Column("rated", sa.Boolean(), nullable=True),
        sa.Column("white_player_id", sa.BigInteger(), nullable=False),
        sa.Column("black_player_id", sa.BigInteger(), nullable=False),
        sa.Column("white_rating", sa.Integer(), nullable=True),
        sa.Column("black_rating", sa.Integer(), nullable=True),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("opening_id", sa.BigInteger(), nullable=True),
        sa.Column("pgn", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("provider IN ('chess_com')", name=op.f("ck_games_provider")),
        sa.CheckConstraint(
            "time_class IN ('rapid', 'blitz', 'bullet', 'daily')", name=op.f("ck_games_time_class")
        ),
        sa.CheckConstraint(
            "result IN ('white_win', 'black_win', 'draw', 'unknown')",
            name=op.f("ck_games_game_result"),
        ),
        sa.CheckConstraint(
            "char_length(provider_game_id) > 0", name=op.f("ck_games_provider_game_id_not_empty")
        ),
        sa.CheckConstraint(
            "white_player_id <> black_player_id", name=op.f("ck_games_distinct_participants")
        ),
        sa.CheckConstraint(
            "white_rating IS NULL OR white_rating >= 0",
            name=op.f("ck_games_white_rating_non_negative"),
        ),
        sa.CheckConstraint(
            "black_rating IS NULL OR black_rating >= 0",
            name=op.f("ck_games_black_rating_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["white_player_id"],
            ["players.id"],
            name=op.f("fk_games_white_player_id_players"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["black_player_id"],
            ["players.id"],
            name=op.f("fk_games_black_player_id_players"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opening_id"],
            ["openings.id"],
            name=op.f("fk_games_opening_id_openings"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_games")),
        sa.UniqueConstraint(
            "provider", "provider_game_id", name=op.f("uq_games_provider_provider_game_id")
        ),
    )
    op.create_index(op.f("ix_games_played_at"), "games", ["played_at"])
    op.create_index(op.f("ix_games_time_class_played_at"), "games", ["time_class", "played_at"])
    op.create_index(op.f("ix_games_white_player_id"), "games", ["white_player_id"])
    op.create_index(op.f("ix_games_black_player_id"), "games", ["black_player_id"])
    op.create_index(op.f("ix_games_opening_id"), "games", ["opening_id"])

    op.create_table(
        "player_games",
        _id(),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("color", sa.String(length=8), nullable=False),
        sa.Column("result", sa.String(length=8), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "color IN ('white', 'black')", name=op.f("ck_player_games_player_color")
        ),
        sa.CheckConstraint(
            "result IN ('win', 'loss', 'draw', 'unknown')",
            name=op.f("ck_player_games_player_result"),
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_player_games_player_id_players"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
            name=op.f("fk_player_games_game_id_games"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_player_games")),
        sa.UniqueConstraint("player_id", "game_id", name=op.f("uq_player_games_player_id_game_id")),
        sa.UniqueConstraint("game_id", "color", name=op.f("uq_player_games_game_id_color")),
    )

    op.create_table(
        "cache_metadata",
        _id(),
        sa.Column("player_id", sa.BigInteger(), nullable=True),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("cache_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "resource_type IN ('player_profile', 'player_stats', 'game_archives', "
            "'game_archive_month')",
            name=op.f("ck_cache_metadata_cache_resource_type"),
        ),
        sa.CheckConstraint(
            "status IN ('refreshing', 'succeeded', 'failed')",
            name=op.f("ck_cache_metadata_cache_status"),
        ),
        sa.CheckConstraint(
            "cache_key = lower(cache_key)", name=op.f("ck_cache_metadata_cache_key_lowercase")
        ),
        sa.CheckConstraint(
            "char_length(cache_key) > 0", name=op.f("ck_cache_metadata_cache_key_not_empty")
        ),
        sa.CheckConstraint(
            "status <> 'succeeded' OR last_success_at IS NOT NULL",
            name=op.f("ck_cache_metadata_succeeded_requires_success_time"),
        ),
        sa.CheckConstraint(
            "status <> 'failed' OR (last_error_code IS NOT NULL AND last_error_at IS NOT NULL)",
            name=op.f("ck_cache_metadata_failed_requires_error"),
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR last_success_at IS NOT NULL",
            name=op.f("ck_cache_metadata_expiry_requires_success"),
        ),
        sa.CheckConstraint(
            "record_count IS NULL OR (record_count >= 0 AND last_success_at IS NOT NULL)",
            name=op.f("ck_cache_metadata_record_count_valid"),
        ),
        sa.CheckConstraint(
            "last_error_code IS NULL OR last_error_code ~ '^[A-Z][A-Z0-9_]*$'",
            name=op.f("ck_cache_metadata_error_code_format"),
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_cache_metadata_player_id_players"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cache_metadata")),
        sa.UniqueConstraint("cache_key", name=op.f("uq_cache_metadata_cache_key")),
    )
    op.create_index(op.f("ix_cache_metadata_expires_at"), "cache_metadata", ["expires_at"])
    op.create_index(op.f("ix_cache_metadata_player_id"), "cache_metadata", ["player_id"])

    op.execute(PLAYER_GAME_CONSISTENCY_SQL)


def downgrade() -> None:
    # Triggers are dropped together with their tables; the functions are not.
    op.drop_table("cache_metadata")
    op.drop_table("player_games")
    op.drop_table("games")
    op.drop_table("openings")
    op.drop_table("players")
    op.execute("DROP FUNCTION IF EXISTS games_consistency_trigger()")
    op.execute("DROP FUNCTION IF EXISTS player_games_consistency_trigger()")
    op.execute("DROP FUNCTION IF EXISTS player_games_validate(bigint)")
