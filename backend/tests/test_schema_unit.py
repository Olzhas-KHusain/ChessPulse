"""Schema rules that can be verified without a database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects import postgresql

import app.models  # noqa: F401  (registers models)
from app.db.base import Base
from app.db.types import UtcDateTime
from app.models import GameResult, PlayerColor, PlayerResult, player_result_for
from app.repositories._batching import chunked, require_lowercase

DIALECT = postgresql.dialect()  # type: ignore[no-untyped-call]


@pytest.mark.parametrize(
    ("color", "result", "expected"),
    [
        (PlayerColor.WHITE, GameResult.WHITE_WIN, PlayerResult.WIN),
        (PlayerColor.BLACK, GameResult.WHITE_WIN, PlayerResult.LOSS),
        (PlayerColor.WHITE, GameResult.BLACK_WIN, PlayerResult.LOSS),
        (PlayerColor.BLACK, GameResult.BLACK_WIN, PlayerResult.WIN),
        (PlayerColor.WHITE, GameResult.DRAW, PlayerResult.DRAW),
        (PlayerColor.BLACK, GameResult.UNKNOWN, PlayerResult.UNKNOWN),
    ],
)
def test_player_result_for(color: PlayerColor, result: GameResult, expected: PlayerResult) -> None:
    assert player_result_for(color, result) is expected


def test_utc_datetime_converts_aware_values_to_utc() -> None:
    almaty = timezone(timedelta(hours=5))
    bound = UtcDateTime().process_bind_param(datetime(2026, 10, 1, 17, tzinfo=almaty), DIALECT)
    assert bound == datetime(2026, 10, 1, 12, tzinfo=UTC)
    assert bound is not None and bound.utcoffset() == timedelta(0)


def test_utc_datetime_rejects_naive_values() -> None:
    with pytest.raises(ValueError, match="naive"):
        UtcDateTime().process_bind_param(datetime(2026, 10, 1, 12), DIALECT)


def test_utc_datetime_normalizes_results_and_passes_none() -> None:
    almaty = timezone(timedelta(hours=5))
    result = UtcDateTime().process_result_value(datetime(2026, 10, 1, 17, tzinfo=almaty), DIALECT)
    assert result == datetime(2026, 10, 1, 12, tzinfo=UTC) and result.tzinfo is UTC
    assert UtcDateTime().process_bind_param(None, DIALECT) is None


def test_mvp_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == {
        "players",
        "games",
        "player_games",
        "openings",
        "cache_metadata",
    }


def test_every_timestamp_column_is_timezone_aware() -> None:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, UtcDateTime) or column.name.endswith("_at"):
                assert isinstance(column.type, UtcDateTime), f"{table.name}.{column.name}"


def test_chunked_and_lowercase_helpers() -> None:
    assert [list(c) for c in chunked([1, 2, 3, 4, 5], 2)] == [[1, 2], [3, 4], [5]]
    with pytest.raises(ValueError):
        list(chunked([1], 0))
    require_lowercase("alice", "username")
    for bad in ("", "Alice"):
        with pytest.raises(ValueError):
            require_lowercase(bad, "username")
