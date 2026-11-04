"""Report scope: which time class and how many days one request covers.

The stored dataset covers the last ``DATASET_WINDOW_DAYS`` days of standard-chess
games of **all** time classes (see ``ingestion.md``). The scope therefore only ever
*narrows* the stored data at read time; it never triggers a different upstream fetch.

* ``time_class`` selects ``rapid`` / ``blitz`` / ``bullet`` / ``daily``, or ``all``
  (stored as ``None``) to combine them.
* ``days`` is one of the published period options and can never exceed the stored
  dataset window, so the numbers are always computed from a complete dataset.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.analytics.window import WINDOW_DAYS
from app.core.config import Settings
from app.models import TimeClass
from app.services.errors import InvalidParameterError

PERIOD_OPTIONS: tuple[int, ...] = (7, 30, 90, 180, 365)
TIME_CLASS_OPTIONS: tuple[str, ...] = ("rapid", "blitz", "bullet", "daily", "all")


@dataclass(frozen=True, slots=True)
class Scope:
    """Validated ``(time_class, days)`` pair shared by every read endpoint."""

    time_class: TimeClass | None  # None = every stored class ("all")
    days: int

    @property
    def time_class_value(self) -> str:
        return "all" if self.time_class is None else self.time_class.value

    @property
    def key(self) -> str:
        """Stable key for request deduplication and UI state."""
        return f"{self.time_class_value}|{self.days}"


def parse_scope(settings: Settings, time_class: str, days: int) -> Scope:
    """Validate query-parameter values against the published options."""
    if days not in PERIOD_OPTIONS:
        options = ", ".join(str(option) for option in PERIOD_OPTIONS)
        raise InvalidParameterError("days", f"days must be one of: {options}")
    if days > settings.dataset_window_days:
        raise InvalidParameterError(
            "days", f"days cannot exceed the stored dataset window ({settings.dataset_window_days})"
        )
    if time_class not in TIME_CLASS_OPTIONS:
        raise InvalidParameterError(
            "time_class", f"time_class must be one of: {', '.join(TIME_CLASS_OPTIONS)}"
        )
    return Scope(
        time_class=None if time_class == "all" else TimeClass(time_class),
        days=days,
    )


# The pre-scaling behaviour (Rapid, 30 days) stays the default for every endpoint,
# so existing clients and links keep working.
DEFAULT_SCOPE = Scope(time_class=TimeClass.RAPID, days=WINDOW_DAYS)
