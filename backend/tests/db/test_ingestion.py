"""Ingestion service against a real database with an in-memory provider."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.window import analysis_window
from app.models import (
    CacheMetadata,
    CacheStatus,
    Game,
    GameResult,
    Opening,
    Player,
    PlayerColor,
    PlayerGame,
    PlayerResult,
    TimeClass,
)
from app.providers.errors import ProviderError, ProviderErrorCode
from app.providers.types import ArchiveMonth, ExcludedGame, ExclusionReason, ProviderOpening
from app.services.ingestion import GameIngestionService, month_cache_key
from tests.ingestion_helpers import NOW, OWNER, FakeProvider, game

pytestmark = pytest.mark.integration

WINDOW = analysis_window(NOW)
SEPT, OCT, AUG = ArchiveMonth(2026, 9), ArchiveMonth(2026, 10), ArchiveMonth(2026, 8)
DAY = timedelta(days=1)


def _count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def _perspectives(session: Session) -> dict[str, tuple[PlayerColor, PlayerResult]]:
    rows = session.execute(
        select(Game.provider_game_id, PlayerGame.color, PlayerGame.result)
        .join(PlayerGame, PlayerGame.game_id == Game.id)
        .join(Player, Player.id == PlayerGame.player_id)
        .where(Player.username == OWNER)
    )
    return {gid: (color, result) for gid, color, result in rows}


def _ingest(session: Session, provider: FakeProvider):  # type: ignore[no-untyped-def]
    return GameIngestionService(session, provider).ingest_player(OWNER, NOW)


def test_only_eligible_rapid_games_in_the_window_are_persisted(session: Session) -> None:
    provider = FakeProvider(
        months={
            AUG: [game(WINDOW.start - DAY, game_id="live:1")],  # month not fetched
            SEPT: [
                game(WINDOW.start - timedelta(seconds=1), game_id="live:2"),  # before window
                game(WINDOW.start, game_id="live:3"),  # inclusive start
                game(WINDOW.start + DAY, game_id="live:4", time_class=TimeClass.BLITZ),
                game(WINDOW.start + DAY, game_id="live:5", rules="chess960"),
                game(WINDOW.start + DAY, game_id="live:6", rules=None),
            ],
            OCT: [
                game(WINDOW.end - timedelta(microseconds=1), game_id="live:7"),
                game(WINDOW.end, game_id="live:8"),  # exclusive end
            ],
        }
    )
    report = _ingest(session, provider)

    assert "month:2026-08" not in provider.calls
    assert sorted(_perspectives(session)) == ["live:3", "live:7"]
    assert _count(session, Game) == 2
    assert report.eligible_games == 2
    assert report.excluded == {
        "outside_window": 2,
        "not_rapid": 1,
        "non_standard_variant": 1,
        "rules_unverified": 1,
    }
    assert report.complete


def test_outcomes_follow_the_searched_players_perspective(session: Session) -> None:
    t = WINDOW.start + DAY
    provider = FakeProvider(
        months={
            OCT: [
                game(t, game_id="live:11", owner_color="white", result=GameResult.WHITE_WIN),
                game(t, game_id="live:12", owner_color="white", result=GameResult.BLACK_WIN),
                game(t, game_id="live:13", owner_color="black", result=GameResult.BLACK_WIN),
                game(t, game_id="live:14", owner_color="black", result=GameResult.WHITE_WIN),
                game(t, game_id="live:15", owner_color="black", result=GameResult.DRAW),
                game(t, game_id="live:16", owner_color="white", result=GameResult.UNKNOWN),
            ]
        }
    )
    _ingest(session, provider)
    assert _perspectives(session) == {
        "live:11": (PlayerColor.WHITE, PlayerResult.WIN),
        "live:12": (PlayerColor.WHITE, PlayerResult.LOSS),
        "live:13": (PlayerColor.BLACK, PlayerResult.WIN),
        "live:14": (PlayerColor.BLACK, PlayerResult.LOSS),
        "live:15": (PlayerColor.BLACK, PlayerResult.DRAW),
        "live:16": (PlayerColor.WHITE, PlayerResult.UNKNOWN),  # never silently a loss
    }


def test_repeated_ingestion_does_not_duplicate(session: Session) -> None:
    games = [game(WINDOW.start + DAY * i, game_id=f"live:{20 + i}") for i in range(1, 4)]
    # The same game also appears in an overlapping archive.
    provider = FakeProvider(months={SEPT: games[:2], OCT: [games[1], games[2]]})

    first = _ingest(session, provider)
    second = _ingest(session, provider)

    assert first.eligible_games == second.eligible_games == 3
    assert second.excluded == {"duplicate_across_archives": 1}
    assert _count(session, Game) == 3
    assert _count(session, PlayerGame) == 3
    assert _count(session, Player) == 2


def test_malformed_records_do_not_block_valid_ones(session: Session) -> None:
    provider = FakeProvider(
        months={OCT: [game(WINDOW.start + DAY, game_id="live:31")]},
        excluded={
            OCT: [
                ExcludedGame(1, ExclusionReason.MISSING_END_TIME, "live:32"),
                ExcludedGame(2, ExclusionReason.NOT_AN_OBJECT),
            ]
        },
    )
    report = _ingest(session, provider)
    assert list(_perspectives(session)) == ["live:31"]
    assert report.excluded == {"missing_end_time": 1, "not_an_object": 1}


def test_failed_month_marks_ingestion_incomplete_and_keeps_last_success(
    session: Session,
) -> None:
    good = [game(WINDOW.start + DAY, game_id="live:41")]
    _ingest(session, FakeProvider(months={SEPT: good, OCT: []}))

    outage = ProviderError(ProviderErrorCode.UPSTREAM_TIMEOUT, "timeout")
    report = _ingest(session, FakeProvider(months={SEPT: outage, OCT: []}))

    assert not report.complete
    assert report.months_failed == {"2026-09": "UPSTREAM_TIMEOUT"}
    assert list(_perspectives(session)) == ["live:41"]  # nothing was deleted
    state = session.scalars(
        select(CacheMetadata).where(CacheMetadata.cache_key == month_cache_key(OWNER, SEPT))
    ).one()
    assert state.status is CacheStatus.FAILED
    assert state.last_error_code == "UPSTREAM_TIMEOUT"
    assert state.last_success_at == NOW  # last good fetch preserved
    oct_state = session.scalars(
        select(CacheMetadata).where(CacheMetadata.cache_key == month_cache_key(OWNER, OCT))
    ).one()
    assert (oct_state.status, oct_state.record_count) == (CacheStatus.SUCCEEDED, 0)


def test_missing_player_writes_nothing(session: Session) -> None:
    provider = FakeProvider(
        profile_error=ProviderError(ProviderErrorCode.PLAYER_NOT_FOUND, "missing")
    )
    with pytest.raises(ProviderError) as excinfo:
        _ingest(session, provider)
    assert excinfo.value.is_confirmed_missing_player
    assert _count(session, Player) == 0


def test_stats_failure_is_reported_without_blocking_games(session: Session) -> None:
    provider = FakeProvider(
        months={OCT: [game(WINDOW.start + DAY)]},
        stats_error=ProviderError(ProviderErrorCode.UPSTREAM_UNAVAILABLE, "down"),
    )
    report = _ingest(session, provider)
    assert report.stats_error == "UPSTREAM_UNAVAILABLE"
    assert report.eligible_games == 1
    owner = session.scalars(select(Player).where(Player.username == OWNER)).one()
    assert owner.current_rapid_rating is None  # not invented


def test_rating_and_opening_are_persisted(session: Session) -> None:
    opening = ProviderOpening("Sicilian-Defense", "Sicilian Defense", "B20")
    _ingest(session, FakeProvider(months={OCT: [game(WINDOW.start + DAY, opening=opening)]}))
    owner = session.scalars(select(Player).where(Player.username == OWNER)).one()
    assert owner.current_rapid_rating == 1523
    stored = session.scalars(select(Opening)).one()
    assert (stored.source_opening_id, stored.eco_code) == ("Sicilian-Defense", "B20")
    assert session.scalars(select(Game.opening_id)).one() == stored.id


def test_confirmed_rename_updates_the_existing_player(session: Session) -> None:
    _ingest(session, FakeProvider(months={OCT: [game(WINDOW.start + DAY, game_id="live:51")]}))
    renamed = FakeProvider(username="new_name", months={OCT: []})
    report = _ingest(session, renamed)

    names = session.scalars(select(Player.username).order_by(Player.id)).all()
    assert names == ["new_name", "rival"]
    assert report.username == "new_name"
    assert _count(session, PlayerGame) == 1
