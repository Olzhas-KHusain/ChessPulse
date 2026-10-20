"""Repository behavior against a real PostgreSQL database."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
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
    TimeClass,
)
from app.repositories import (
    CacheMetadataRepository,
    CacheState,
    GameRecord,
    GameRepository,
    OpeningRecord,
    OpeningRepository,
    PageCursor,
    PlayerProfile,
    PlayerRepository,
)
from tests.db.factories import T0

pytestmark = pytest.mark.integration

CHESS_COM = Provider.CHESS_COM


def _count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def _record(white: int, black: int, game_id: str = "live:1", **fields: object) -> GameRecord:
    values: dict[str, object] = {
        "provider": CHESS_COM,
        "provider_game_id": game_id,
        "played_at": T0,
        "time_class": TimeClass.RAPID,
        "result": GameResult.WHITE_WIN,
        "white_player_id": white,
        "black_player_id": black,
    }
    values.update(fields)
    return GameRecord(**values)  # type: ignore[arg-type]


@pytest.fixture
def players(session: Session) -> dict[str, int]:
    ids = PlayerRepository(session).ensure_usernames(CHESS_COM, ["me", "rival", "other"])
    session.commit()
    return ids


# --- players ------------------------------------------------------------------------


def test_ensure_usernames_is_idempotent_and_returns_ids(session: Session) -> None:
    repo = PlayerRepository(session)
    first = repo.ensure_usernames(CHESS_COM, ["alice", "bob", "alice"])
    second = repo.ensure_usernames(CHESS_COM, ["bob", "alice", "carol"])
    session.commit()

    assert set(first) == {"alice", "bob"}
    assert first["alice"] == second["alice"] and first["bob"] == second["bob"]
    assert _count(session, Player) == 3


def test_ensure_usernames_rejects_unnormalized_input(session: Session) -> None:
    with pytest.raises(ValueError, match="lowercase"):
        PlayerRepository(session).ensure_usernames(CHESS_COM, ["Alice"])


def test_upsert_profile_then_ensure_does_not_erase_profile(session: Session) -> None:
    repo = PlayerRepository(session)
    repo.upsert_profile(
        PlayerProfile(
            provider=CHESS_COM,
            username="alice",
            provider_player_id="41",
            display_name="Alice A.",
            profile_url="https://www.chess.com/member/Alice",
        )
    )
    repo.ensure_usernames(CHESS_COM, ["alice"])
    session.commit()

    stored = repo.get_by_username(CHESS_COM, "alice")
    assert stored is not None
    assert stored.display_name == "Alice A."
    assert stored.provider_player_id == "41"
    assert stored.avatar_url is None


def test_upsert_profile_updates_and_clears_fields(session: Session) -> None:
    repo = PlayerRepository(session)
    first = repo.upsert_profile(
        PlayerProfile(provider=CHESS_COM, username="alice", avatar_url="https://img/a.png")
    )
    session.commit()
    second = repo.upsert_profile(
        PlayerProfile(provider=CHESS_COM, username="alice", display_name="Alice")
    )
    session.commit()

    assert second.id == first.id
    assert second.display_name == "Alice"
    assert second.avatar_url is None
    assert _count(session, Player) == 1


def test_profile_with_existing_player_id_under_new_username_is_rejected(session: Session) -> None:
    """A rename must be resolved explicitly by the provider layer, never silently."""
    repo = PlayerRepository(session)
    repo.upsert_profile(PlayerProfile(provider=CHESS_COM, username="old", provider_player_id="7"))
    session.commit()
    with pytest.raises(IntegrityError):
        repo.upsert_profile(
            PlayerProfile(provider=CHESS_COM, username="new", provider_player_id="7")
        )
    session.rollback()


def test_set_current_rapid_rating(session: Session) -> None:
    repo = PlayerRepository(session)
    player_id = repo.ensure_usernames(CHESS_COM, ["alice"])["alice"]
    repo.set_current_rapid_rating(player_id, 1523, T0)
    session.commit()
    stored = repo.get_by_username(CHESS_COM, "alice")
    assert stored is not None
    assert (stored.current_rapid_rating, stored.current_rapid_rating_at) == (1523, T0)


# --- games: duplicate-safe upsert -------------------------------------------------


def test_upserting_the_same_games_twice_creates_no_duplicates(
    session: Session, players: dict[str, int]
) -> None:
    repo = GameRepository(session)
    records = [
        _record(players["me"], players["rival"], "live:1"),
        _record(players["rival"], players["me"], "live:2", result=GameResult.DRAW),
    ]
    first = repo.upsert_games(records)
    session.commit()
    second = repo.upsert_games(records)  # overlapping archive fetch
    session.commit()

    assert first == second
    assert _count(session, Game) == 2


def test_duplicate_keys_within_one_batch_are_stored_once(
    session: Session, players: dict[str, int]
) -> None:
    repo = GameRepository(session)
    ids = repo.upsert_games(
        [
            _record(players["me"], players["rival"], "live:1", white_rating=1500),
            _record(players["me"], players["rival"], "live:1", white_rating=1510),
        ]
    )
    session.commit()
    assert len(ids) == 1
    assert session.scalars(select(Game.white_rating)).one() == 1510


def test_unchanged_upsert_does_not_touch_updated_at(
    session: Session, players: dict[str, int]
) -> None:
    repo = GameRepository(session)
    record = _record(players["me"], players["rival"])
    repo.upsert_games([record])
    session.commit()
    before = session.scalars(select(Game.updated_at)).one()

    repo.upsert_games([record])
    session.commit()
    assert session.scalars(select(Game.updated_at)).one() == before


def test_upsert_never_erases_known_optional_values(
    session: Session, players: dict[str, int]
) -> None:
    repo = GameRepository(session)
    repo.upsert_games(
        [
            _record(
                players["me"],
                players["rival"],
                pgn="1. e4 e5",
                white_rating=1500,
                game_url="https://www.chess.com/game/live/1",
            )
        ]
    )
    session.commit()
    repo.upsert_games([_record(players["me"], players["rival"], black_rating=1480)])
    session.commit()

    session.expire_all()
    game = session.scalars(select(Game)).one()
    assert (game.pgn, game.white_rating, game.black_rating) == ("1. e4 e5", 1500, 1480)
    assert game.game_url == "https://www.chess.com/game/live/1"


def test_upsert_rejects_naive_timestamps(session: Session, players: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        GameRepository(session).upsert_games(
            [_record(players["me"], players["rival"], played_at=T0.replace(tzinfo=None))]
        )


# --- player_games ---------------------------------------------------------------------


def test_link_player_games_is_idempotent_and_derives_results(
    session: Session, players: dict[str, int]
) -> None:
    repo = GameRepository(session)
    ids = repo.upsert_games(
        [
            _record(players["me"], players["rival"], "live:1", result=GameResult.WHITE_WIN),
            _record(players["rival"], players["me"], "live:2", result=GameResult.WHITE_WIN),
            _record(players["rival"], players["me"], "live:3", result=GameResult.DRAW),
        ]
    )
    links = [
        (ids[(CHESS_COM, "live:1")], PlayerColor.WHITE, GameResult.WHITE_WIN),
        (ids[(CHESS_COM, "live:2")], PlayerColor.BLACK, GameResult.WHITE_WIN),
        (ids[(CHESS_COM, "live:3")], PlayerColor.BLACK, GameResult.DRAW),
    ]
    repo.link_player_games(players["me"], links)
    session.commit()
    repo.link_player_games(players["me"], links)
    session.commit()

    results = session.scalars(select(PlayerGame.result).order_by(PlayerGame.game_id)).all()
    assert results == [PlayerResult.WIN, PlayerResult.LOSS, PlayerResult.DRAW]


def test_link_with_wrong_color_fails_at_commit(session: Session, players: dict[str, int]) -> None:
    repo = GameRepository(session)
    ids = repo.upsert_games([_record(players["me"], players["rival"])])
    repo.link_player_games(
        players["me"], [(ids[(CHESS_COM, "live:1")], PlayerColor.BLACK, GameResult.WHITE_WIN)]
    )
    with pytest.raises(IntegrityError) as excinfo:
        session.commit()
    session.rollback()
    diag = excinfo.value.orig.diag  # type: ignore[union-attr]
    assert diag.constraint_name == "ck_player_games_participant"


# --- windowed queries ---------------------------------------------------------------


def _seed_window(session: Session, players: dict[str, int]) -> GameRepository:
    """Games relative to a window [T0, T0 + 30 days)."""
    repo = GameRepository(session)
    me, rival, other = players["me"], players["rival"], players["other"]
    end = T0 + timedelta(days=30)
    records = [
        _record(me, rival, "live:start", played_at=T0),  # inclusive lower bound
        _record(me, rival, "live:mid-a", played_at=T0 + timedelta(days=5)),
        _record(rival, me, "live:mid-b", played_at=T0 + timedelta(days=5)),  # same timestamp
        _record(me, rival, "live:last", played_at=end - timedelta(microseconds=1)),
        _record(me, rival, "live:end", played_at=end),  # exclusive upper bound
        _record(me, rival, "live:before", played_at=T0 - timedelta(microseconds=1)),
        _record(me, rival, "live:blitz", time_class=TimeClass.BLITZ),
        _record(rival, other, "live:not-mine", played_at=T0 + timedelta(days=1)),
    ]
    ids = repo.upsert_games(records)
    repo.link_player_games(
        me,
        [
            (
                ids[r.key],
                PlayerColor.WHITE if r.white_player_id == me else PlayerColor.BLACK,
                r.result,
            )
            for r in records
            if me in (r.white_player_id, r.black_player_id)
        ],
    )
    session.commit()
    return repo


def test_list_player_games_applies_window_mode_and_ownership(
    session: Session, players: dict[str, int]
) -> None:
    repo = _seed_window(session, players)
    rows = repo.list_player_games(players["me"], start=T0, end=T0 + timedelta(days=30))

    # Excluded: the exclusive end bound, a game before the window, a Blitz game, and a
    # game the player did not take part in. Equal timestamps: higher game id first.
    by_id = {row.game.provider_game_id: row.game.id for row in rows}
    assert by_id["live:mid-b"] > by_id["live:mid-a"]
    assert [row.game.provider_game_id for row in rows] == [
        "live:last",
        "live:mid-b",
        "live:mid-a",
        "live:start",
    ]
    assert [row.perspective.color for row in rows] == [
        PlayerColor.WHITE,
        PlayerColor.BLACK,
        PlayerColor.WHITE,
        PlayerColor.WHITE,
    ]


def test_list_player_games_paginates_deterministically(
    session: Session, players: dict[str, int]
) -> None:
    repo = _seed_window(session, players)
    start, end = T0, T0 + timedelta(days=30)
    full = [r.game.id for r in repo.list_player_games(players["me"], start=start, end=end)]

    seen: list[int] = []
    cursor: PageCursor | None = None
    while True:
        page = repo.list_player_games(players["me"], start=start, end=end, limit=1, after=cursor)
        if not page:
            break
        seen.extend(r.game.id for r in page)
        last = page[-1].game
        cursor = PageCursor(played_at=last.played_at, game_id=last.id)
    assert seen == full


def test_list_player_games_loads_related_rows_in_one_query(
    session: Session, players: dict[str, int]
) -> None:
    repo = _seed_window(session, players)
    statements: list[str] = []

    def _capture(*args: object) -> None:
        statements.append(str(args[2]))

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", _capture)
    try:
        session.expire_all()
        rows = repo.list_player_games(players["me"], start=T0, end=T0 + timedelta(days=30))
        opponents = {
            (
                r.game.black_player
                if r.perspective.color is PlayerColor.WHITE
                else r.game.white_player
            ).username
            for r in rows
        }
        openings = {r.game.opening for r in rows}
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert opponents == {"rival"}
    assert openings == {None}
    assert len(statements) == 1


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"limit": 0}, "limit"),
        ({"limit": 201}, "limit"),
        ({"start": T0 + timedelta(days=1), "end": T0}, "earlier"),
        ({"start": T0.replace(tzinfo=None)}, "timezone-aware"),
    ],
)
def test_list_player_games_validates_arguments(
    session: Session, kwargs: dict[str, object], message: str
) -> None:
    params: dict[str, object] = {"start": T0, "end": T0 + timedelta(days=30)}
    params.update(kwargs)
    with pytest.raises(ValueError, match=message):
        GameRepository(session).list_player_games(1, **params)  # type: ignore[arg-type]


# --- openings ---------------------------------------------------------------------


def test_ensure_openings_is_idempotent_and_keeps_known_eco(session: Session) -> None:
    repo = OpeningRepository(session)
    key = (OpeningSource.CHESS_COM, "sicilian-defense")
    first = repo.ensure_openings(
        [OpeningRecord(OpeningSource.CHESS_COM, "sicilian-defense", "Sicilian Defense", "B20")]
    )
    second = repo.ensure_openings(
        [OpeningRecord(OpeningSource.CHESS_COM, "sicilian-defense", "Sicilian Defense")]
    )
    session.commit()

    assert first[key] == second[key]
    assert repo.ensure_openings([]) == {}
    opening = session.scalars(select(Opening)).one()
    assert opening.eco_code == "B20"


# --- cache metadata ---------------------------------------------------------------


def test_cache_metadata_save_and_get(session: Session) -> None:
    repo = CacheMetadataRepository(session)
    key = "chess_com:game_archive_month:alice:2026-10"
    repo.save(
        CacheState(
            cache_key=key,
            resource_type=CacheResourceType.GAME_ARCHIVE_MONTH,
            status=CacheStatus.SUCCEEDED,
            last_attempt_at=T0,
            last_success_at=T0,
            expires_at=T0 + timedelta(hours=12),
            record_count=0,
        )
    )
    session.commit()
    repo.save(
        CacheState(
            cache_key=key,
            resource_type=CacheResourceType.GAME_ARCHIVE_MONTH,
            status=CacheStatus.FAILED,
            last_attempt_at=T0 + timedelta(hours=13),
            last_success_at=T0,
            expires_at=T0 + timedelta(hours=12),
            record_count=0,
            last_error_code="UPSTREAM_RATE_LIMITED",
            last_error_at=T0 + timedelta(hours=13),
        )
    )
    session.commit()

    stored = repo.get_by_key(key)
    assert stored is not None
    assert stored.status is CacheStatus.FAILED
    assert stored.last_success_at == T0  # last known good is preserved
    assert stored.record_count == 0
    assert repo.get_by_key("chess_com:player_profile:nobody") is None
