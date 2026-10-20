"""Database-level constraints: uniqueness, foreign keys, checks, triggers, UTC handling."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.models import (
    CacheMetadata,
    CacheResourceType,
    CacheStatus,
    Game,
    GameResult,
    Opening,
    OpeningSource,
    Player,
    PlayerColor,
    PlayerGame,
    PlayerResult,
    Provider,
)
from tests.db.factories import T0, make_game, make_player

pytestmark = pytest.mark.integration


@contextmanager
def violates(session: Session, constraint: str) -> Iterator[None]:
    """Assert that the block (including its commit) violates ``constraint``."""
    with pytest.raises(IntegrityError) as excinfo:
        yield
        session.commit()
    session.rollback()
    orig = excinfo.value.orig
    assert orig is not None
    assert getattr(orig.diag, "constraint_name", None) == constraint  # type: ignore[attr-defined]


def _link(
    session: Session, player: Player, game: Game, color: PlayerColor, result: PlayerResult
) -> None:
    session.add(PlayerGame(player_id=player.id, game_id=game.id, color=color, result=result))
    session.flush()


# --- players -------------------------------------------------------------------


def test_player_username_is_unique_per_provider(session: Session) -> None:
    make_player(session, "alice")
    session.commit()
    with violates(session, "uq_players_provider_username"):
        make_player(session, "alice")


def test_player_username_must_be_stored_lowercase(session: Session) -> None:
    with violates(session, "ck_players_username_lowercase"):
        make_player(session, "Alice")


def test_provider_player_id_is_unique_when_present_and_nulls_are_allowed(
    session: Session,
) -> None:
    make_player(session, "no_id_1")
    make_player(session, "no_id_2")
    make_player(session, "with_id", provider_player_id="41")
    session.commit()
    with violates(session, "uq_players_provider_provider_player_id"):
        make_player(session, "renamed", provider_player_id="41")


def test_player_optional_fields_stay_null(session: Session) -> None:
    player = make_player(session, "minimal")
    session.commit()
    session.expire_all()
    stored = session.get_one(Player, player.id)
    assert stored.provider_player_id is None
    assert stored.display_name is None
    assert stored.profile_url is None
    assert stored.avatar_url is None
    assert stored.current_rapid_rating is None
    assert stored.current_rapid_rating_at is None


def test_rating_timestamp_requires_a_rating(session: Session) -> None:
    with violates(session, "ck_players_current_rapid_rating_at_requires_rating"):
        make_player(session, "ghost", current_rapid_rating_at=T0)


# --- games ---------------------------------------------------------------------


def test_duplicate_provider_game_id_is_rejected(session: Session) -> None:
    white, black = make_player(session), make_player(session)
    make_game(session, white, black, provider_game_id="live:1001")
    session.commit()
    with violates(session, "uq_games_provider_provider_game_id"):
        make_game(session, white, black, provider_game_id="live:1001")


def test_game_requires_two_distinct_participants(session: Session) -> None:
    player = make_player(session)
    with violates(session, "ck_games_distinct_participants"):
        make_game(session, player, player)


def test_game_rejects_unknown_time_class(session: Session) -> None:
    white, black = make_player(session), make_player(session)
    session.commit()
    with violates(session, "ck_games_time_class"):
        session.execute(
            text(
                "INSERT INTO games (provider, provider_game_id, played_at, time_class, result, "
                "white_player_id, black_player_id) "
                "VALUES ('chess_com', 'live:9', now(), 'hyperbullet', 'draw', :w, :b)"
            ),
            {"w": white.id, "b": black.id},
        )


def test_game_rejects_negative_rating(session: Session) -> None:
    white, black = make_player(session), make_player(session)
    with violates(session, "ck_games_white_rating_non_negative"):
        make_game(session, white, black, white_rating=-1)


def test_game_optional_source_fields_stay_null(session: Session) -> None:
    white, black = make_player(session), make_player(session)
    game = make_game(session, white, black, result=GameResult.UNKNOWN)
    session.commit()
    session.expire_all()
    stored = session.get_one(Game, game.id)
    for field in (
        "game_url",
        "time_control",
        "rated",
        "white_rating",
        "black_rating",
        "opening_id",
        "pgn",
    ):
        assert getattr(stored, field) is None, field
    assert stored.result is GameResult.UNKNOWN


def test_game_with_missing_player_is_rejected(session: Session) -> None:
    white = make_player(session)
    session.commit()
    with violates(session, "fk_games_black_player_id_players"):
        session.add(
            Game(
                provider=Provider.CHESS_COM,
                provider_game_id="live:404",
                played_at=T0,
                time_class="rapid",
                result=GameResult.DRAW,
                white_player_id=white.id,
                black_player_id=999_999,
            )
        )
        session.flush()


def test_player_referenced_by_a_game_cannot_be_deleted(session: Session) -> None:
    white, black = make_player(session), make_player(session)
    make_game(session, white, black)
    session.commit()
    with violates(session, "fk_games_white_player_id_players"):
        session.execute(text("DELETE FROM players WHERE id = :id"), {"id": white.id})


def test_deleting_an_opening_keeps_the_game(session: Session) -> None:
    opening = Opening(source=OpeningSource.CHESS_COM, source_opening_id="x", name="X")
    session.add(opening)
    session.flush()
    game = make_game(session, make_player(session), make_player(session), opening_id=opening.id)
    session.commit()

    session.execute(text("DELETE FROM openings WHERE id = :id"), {"id": opening.id})
    session.commit()
    session.expire_all()
    assert session.get_one(Game, game.id).opening_id is None


# --- player_games ----------------------------------------------------------------


def test_player_cannot_be_linked_to_the_same_game_twice(session: Session) -> None:
    white, black = make_player(session), make_player(session)
    game = make_game(session, white, black)
    _link(session, white, game, PlayerColor.WHITE, PlayerResult.WIN)
    session.commit()
    with violates(session, "uq_player_games_player_id_game_id"):
        _link(session, white, game, PlayerColor.WHITE, PlayerResult.WIN)


def test_only_one_perspective_per_side(session: Session) -> None:
    white, black = make_player(session), make_player(session)
    game = make_game(session, white, black)
    _link(session, white, game, PlayerColor.WHITE, PlayerResult.WIN)
    session.commit()
    with violates(session, "uq_player_games_game_id_color"):
        _link(session, black, game, PlayerColor.WHITE, PlayerResult.WIN)


def test_link_must_match_a_game_participant(session: Session) -> None:
    white, black, outsider = make_player(session), make_player(session), make_player(session)
    game = make_game(session, white, black)
    session.commit()
    with violates(session, "ck_player_games_participant"):
        _link(session, outsider, game, PlayerColor.BLACK, PlayerResult.LOSS)


def test_link_color_must_match_the_participant_side(session: Session) -> None:
    white, black = make_player(session), make_player(session)
    game = make_game(session, white, black)
    session.commit()
    with violates(session, "ck_player_games_participant"):
        _link(session, white, game, PlayerColor.BLACK, PlayerResult.LOSS)


@pytest.mark.parametrize(
    ("game_result", "color", "wrong_result"),
    [
        (GameResult.WHITE_WIN, PlayerColor.WHITE, PlayerResult.LOSS),
        (GameResult.WHITE_WIN, PlayerColor.BLACK, PlayerResult.WIN),
        (GameResult.BLACK_WIN, PlayerColor.WHITE, PlayerResult.WIN),
        (GameResult.DRAW, PlayerColor.BLACK, PlayerResult.WIN),
        (GameResult.UNKNOWN, PlayerColor.WHITE, PlayerResult.LOSS),
    ],
)
def test_link_result_must_match_the_game_result(
    session: Session, game_result: GameResult, color: PlayerColor, wrong_result: PlayerResult
) -> None:
    white, black = make_player(session), make_player(session)
    game = make_game(session, white, black, result=game_result)
    session.commit()
    player = white if color is PlayerColor.WHITE else black
    with violates(session, "ck_player_games_result_matches_game"):
        _link(session, player, game, color, wrong_result)


def test_changing_a_game_result_alone_is_rejected(session: Session) -> None:
    white, black = make_player(session), make_player(session)
    game = make_game(session, white, black, result=GameResult.WHITE_WIN)
    _link(session, black, game, PlayerColor.BLACK, PlayerResult.LOSS)
    session.commit()
    with violates(session, "ck_player_games_result_matches_game"):
        game.result = GameResult.DRAW
        session.flush()


def test_correcting_a_game_and_its_links_in_one_transaction_is_allowed(session: Session) -> None:
    white, black = make_player(session), make_player(session)
    game = make_game(session, white, black, result=GameResult.WHITE_WIN)
    _link(session, black, game, PlayerColor.BLACK, PlayerResult.LOSS)
    session.commit()

    game.result = GameResult.DRAW
    session.flush()
    session.execute(
        text("UPDATE player_games SET result = 'draw' WHERE game_id = :g"), {"g": game.id}
    )
    session.commit()
    assert session.scalars(select(PlayerGame.result)).one() == PlayerResult.DRAW


def test_deleting_a_game_removes_its_links(session: Session) -> None:
    white, black = make_player(session), make_player(session)
    game = make_game(session, white, black)
    _link(session, white, game, PlayerColor.WHITE, PlayerResult.WIN)
    session.commit()
    session.execute(text("DELETE FROM games WHERE id = :id"), {"id": game.id})
    session.commit()
    assert session.scalars(select(PlayerGame)).all() == []


# --- openings --------------------------------------------------------------------


def test_opening_source_id_is_unique(session: Session) -> None:
    session.add(Opening(source=OpeningSource.CHESS_COM, source_opening_id="sicilian", name="A"))
    session.commit()
    with violates(session, "uq_openings_source_source_opening_id"):
        session.add(Opening(source=OpeningSource.CHESS_COM, source_opening_id="sicilian", name="B"))
        session.flush()


# Longer values are already rejected by the VARCHAR(3) type.
@pytest.mark.parametrize("eco", ["Z99", "B2", "b20", "BB0"])
def test_opening_rejects_malformed_eco_code(session: Session, eco: str) -> None:
    with violates(session, "ck_openings_eco_code_format"):
        session.execute(
            text(
                "INSERT INTO openings (source, source_opening_id, name, eco_code) "
                "VALUES ('chess_com', 'x', 'X', :eco)"
            ),
            {"eco": eco},
        )


# --- cache_metadata ----------------------------------------------------------------


def _cache(**fields: object) -> CacheMetadata:
    values: dict[str, object] = {
        "resource_type": CacheResourceType.PLAYER_PROFILE,
        "cache_key": "chess_com:player_profile:alice",
        "status": CacheStatus.REFRESHING,
        "last_attempt_at": T0,
    }
    values.update(fields)
    return CacheMetadata(**values)


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"status": CacheStatus.SUCCEEDED}, "ck_cache_metadata_succeeded_requires_success_time"),
        ({"status": CacheStatus.FAILED}, "ck_cache_metadata_failed_requires_error"),
        ({"expires_at": T0}, "ck_cache_metadata_expiry_requires_success"),
        ({"record_count": 0}, "ck_cache_metadata_record_count_valid"),
        (
            {"last_success_at": T0, "record_count": -1},
            "ck_cache_metadata_record_count_valid",
        ),
        (
            {"last_error_code": "Traceback (most recent call last)", "last_error_at": T0},
            "ck_cache_metadata_error_code_format",
        ),
        ({"cache_key": "Chess_com:Player_profile:Alice"}, "ck_cache_metadata_cache_key_lowercase"),
    ],
)
def test_cache_metadata_invariants(
    session: Session, fields: dict[str, object], constraint: str
) -> None:
    with violates(session, constraint):
        session.add(_cache(**fields))
        session.flush()


def test_cache_key_is_unique(session: Session) -> None:
    session.add(_cache())
    session.commit()
    with violates(session, "uq_cache_metadata_cache_key"):
        session.add(_cache())
        session.flush()


def test_failed_refresh_can_keep_the_last_success(session: Session) -> None:
    session.add(
        _cache(
            status=CacheStatus.FAILED,
            last_success_at=T0,
            expires_at=T0 + timedelta(hours=12),
            record_count=0,
            last_error_code="UPSTREAM_TIMEOUT",
            last_error_at=T0 + timedelta(hours=13),
        )
    )
    session.commit()


def test_deleting_a_player_removes_its_cache_metadata(session: Session) -> None:
    player = make_player(session)
    session.add(_cache(player_id=player.id))
    session.commit()
    session.execute(text("DELETE FROM players WHERE id = :id"), {"id": player.id})
    session.commit()
    assert session.scalars(select(CacheMetadata)).all() == []


# --- UTC handling ----------------------------------------------------------------


def test_timestamps_round_trip_as_utc_regardless_of_session_time_zone(session: Session) -> None:
    almaty = timezone(timedelta(hours=5))
    white, black = make_player(session), make_player(session)
    game = make_game(session, white, black, played_at=datetime(2026, 10, 1, 17, 0, tzinfo=almaty))
    session.commit()

    session.execute(text("SET TIME ZONE 'America/New_York'"))
    session.expire_all()
    stored = session.get_one(Game, game.id)
    assert stored.played_at == datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    assert stored.played_at.utcoffset() == timedelta(0)
    assert stored.created_at.utcoffset() == timedelta(0)


def test_naive_datetimes_are_rejected(session: Session) -> None:
    white, black = make_player(session), make_player(session)
    with pytest.raises(StatementError, match="naive datetime"):
        make_game(session, white, black, played_at=datetime(2026, 10, 1, 12, 0))
    session.rollback()
