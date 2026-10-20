"""Shared analysis window and the Rapid eligibility rule (no database)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.analytics.window import AnalysisWindow, analysis_window
from app.models import GameResult, TimeClass
from app.services.eligibility import IneligibleReason, ineligibility_reason
from tests.ingestion_helpers import NOW, game

WINDOW = analysis_window(NOW)


def test_window_is_30_days_start_inclusive_end_exclusive() -> None:
    assert WINDOW.end == NOW
    assert WINDOW.start == NOW - timedelta(days=30)
    assert WINDOW.contains(WINDOW.start)
    assert not WINDOW.contains(WINDOW.end)
    assert WINDOW.contains(WINDOW.end - timedelta(microseconds=1))
    assert not WINDOW.contains(WINDOW.start - timedelta(microseconds=1))


def test_window_normalizes_other_time_zones_to_utc() -> None:
    almaty_now = NOW.astimezone(timezone(timedelta(hours=5)))
    window = analysis_window(almaty_now)
    assert window == WINDOW
    assert window.end.tzinfo is UTC


def test_window_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError):
        analysis_window(datetime(2026, 10, 20))
    with pytest.raises(ValueError):
        WINDOW.contains(datetime(2026, 10, 1))
    with pytest.raises(ValueError):
        AnalysisWindow(NOW, NOW)


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, None),
        ({"result": GameResult.UNKNOWN}, None),  # unknown result stays eligible, not a loss
        ({"time_class": TimeClass.BLITZ}, IneligibleReason.NOT_RAPID),
        ({"time_class": TimeClass.DAILY}, IneligibleReason.NOT_RAPID),
        ({"rules": "chess960"}, IneligibleReason.VARIANT),
        ({"rules": None}, IneligibleReason.RULES_UNVERIFIED),
    ],
)
def test_eligibility_rule(kwargs: dict[str, object], expected: IneligibleReason | None) -> None:
    candidate = game(NOW - timedelta(days=1), **kwargs)  # type: ignore[arg-type]
    assert ineligibility_reason(candidate, WINDOW) is expected


@pytest.mark.parametrize(
    ("played_at", "expected"),
    [
        (WINDOW.start, None),
        (WINDOW.end - timedelta(microseconds=1), None),
        (WINDOW.end, IneligibleReason.OUTSIDE_WINDOW),
        (WINDOW.start - timedelta(seconds=1), IneligibleReason.OUTSIDE_WINDOW),
    ],
)
def test_eligibility_window_boundaries(
    played_at: datetime, expected: IneligibleReason | None
) -> None:
    assert ineligibility_reason(game(played_at), WINDOW) is expected
