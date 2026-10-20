"""The single shared analysis-window definition (spec §6.1).

Rolling window of the last 30 days in UTC: ``start = now - 30 days`` (inclusive),
``end = now`` (exclusive). Every module that filters by period must use this.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

WINDOW_DAYS = 30


@dataclass(frozen=True, slots=True)
class AnalysisWindow:
    start: datetime  # inclusive, UTC
    end: datetime  # exclusive, UTC

    def __post_init__(self) -> None:
        for value in (self.start, self.end):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("window bounds must be timezone-aware")
        if self.start >= self.end:
            raise ValueError("start must be earlier than end")

    def contains(self, moment: datetime) -> bool:
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError("moment must be timezone-aware")
        return self.start <= moment < self.end


def analysis_window(now: datetime, days: int = WINDOW_DAYS) -> AnalysisWindow:
    """Window ending at ``now`` (exclusive) and starting ``days`` earlier (inclusive)."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if days <= 0:
        raise ValueError("days must be positive")
    end = now.astimezone(UTC)
    return AnalysisWindow(start=end - timedelta(days=days), end=end)
