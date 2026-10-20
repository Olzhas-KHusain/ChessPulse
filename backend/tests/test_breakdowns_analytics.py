"""Pure rating-history, opening and opponent grouping (no database)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.analytics.breakdowns import (
    UNKNOWN_OPENING_NAME,
    Coverage,
    GameRow,
    GroupSort,
    group_openings,
    group_opponents,
    rating_history,
    sort_groups,
)
from app.models import PlayerColor, PlayerResult

T0 = datetime(2026, 10, 1, tzinfo=UTC)
W, L, D, U = PlayerResult.WIN, PlayerResult.LOSS, PlayerResult.DRAW, PlayerResult.UNKNOWN


def row(i: int, **kw: Any) -> GameRow:
    values: dict[str, Any] = {
        "game_id": i,
        "played_at": T0 + timedelta(hours=i),
        "color": PlayerColor.WHITE,
        "result": W,
        "player_rating": 1500 + i,
        "opponent_id": 100,
        "opponent_username": "rival",
        "opponent_rating": 1400,
        "opening_key": "Sicilian-Defense",
        "opening_name": "Sicilian Defense",
        "eco_code": "B20",
    }
    values.update(kw)
    return GameRow(**values)


def test_rating_history_never_fabricates_points() -> None:
    h = rating_history([row(1), row(5, player_rating=None), row(9)], dataset_complete=True)
    assert [(p.timestamp, p.rating, p.source) for p in h.points] == [
        (T0 + timedelta(hours=1), 1501, "game_record"),
        (T0 + timedelta(hours=9), 1509, "game_record"),
    ]
    assert (h.games_considered, h.games_without_rating) == (3, 1)
    assert h.coverage is Coverage.PARTIAL


def test_rating_history_without_observations() -> None:
    h = rating_history([row(1, player_rating=None)], dataset_complete=True)
    assert h.points == () and h.coverage is Coverage.NONE
    assert rating_history([], dataset_complete=True).coverage is Coverage.NONE


def test_duplicate_observations_are_reported_once() -> None:
    same = T0
    h = rating_history(
        [row(2, played_at=same, player_rating=1500), row(1, played_at=same, player_rating=1500)],
        dataset_complete=True,
    )
    assert [p.game_id for p in h.points] == [1]
    assert h.duplicates_removed == 1
    assert h.coverage is Coverage.COMPLETE


def test_incomplete_dataset_makes_coverage_partial() -> None:
    assert rating_history([row(1)], dataset_complete=False).coverage is Coverage.PARTIAL


def test_openings_group_by_key_with_honest_unknown() -> None:
    groups = group_openings(
        [
            row(1),
            row(2, result=L),
            row(3, opening_key=None, opening_name=None, eco_code=None, result=D),
            row(4, opening_key=None, opening_name=None, eco_code=None, result=U),
            row(5, opening_key="French-Defense", opening_name="French Defense", eco_code="C00"),
        ]
    )
    by_name = {g.name: g for g in groups}
    sicilian = by_name["Sicilian Defense"]
    assert (sicilian.counts.games_count, sicilian.counts.wins, sicilian.counts.losses) == (2, 1, 1)
    assert sicilian.counts.win_rate == 50.0
    unknown = by_name[UNKNOWN_OPENING_NAME]
    assert unknown.is_unknown and unknown.key is None and unknown.eco_code is None
    assert (unknown.counts.games_count, unknown.counts.draws, unknown.counts.unknown_results) == (
        2,
        1,
        1,
    )
    assert unknown.counts.win_rate == 0.0


def test_unknown_only_group_has_null_win_rate() -> None:
    (group,) = group_openings([row(1, opening_key=None, result=U)])
    assert group.counts.games_count == 1 and group.counts.win_rate is None


def test_opponents_are_grouped_by_identity_not_name_similarity() -> None:
    groups = group_opponents(
        [
            row(1, opponent_id=1, opponent_username="magnus_fan"),
            row(2, opponent_id=2, opponent_username="magnus-fan"),
            row(3, opponent_id=3, opponent_username="magnusfan"),
            row(4, opponent_id=1, opponent_username="magnus_fan", opponent_rating=None, result=L),
        ]
    )
    assert sorted((g.username, g.counts.games_count) for g in groups) == [
        ("magnus-fan", 1),
        ("magnus_fan", 2),
        ("magnusfan", 1),
    ]
    first = next(g for g in groups if g.opponent_id == 1)
    assert first.last_played_at == T0 + timedelta(hours=4)
    assert first.last_rating is None  # latest game had no rating; not backfilled


def test_sorting_is_deterministic() -> None:
    groups = group_opponents(
        [
            row(1, opponent_id=1, opponent_username="b"),
            row(2, opponent_id=2, opponent_username="a", result=L),
            row(3, opponent_id=3, opponent_username="c", result=U),
            row(4, opponent_id=1, opponent_username="b", result=L),
        ]
    )

    def names(sort: GroupSort) -> list[str]:
        return [g.username for g in sort_groups(groups, sort, lambda g: g.username)]

    assert names(GroupSort.GAMES) == ["b", "a", "c"]
    assert names(GroupSort.WIN_RATE) == ["b", "a", "c"]  # 50%, 0%, null last
    assert names(GroupSort.NAME) == ["a", "b", "c"]
