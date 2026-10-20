"""Cache freshness policy for a player's dataset.

States (derived at read time from ``cache_metadata``; never stored as text):

* ``missing``   — no successful refresh has ever been recorded (cache miss).
* ``fresh``     — last success is younger than the TTL; served without upstream calls.
* ``expired``   — TTL elapsed; a controlled refresh is attempted.
* ``cooldown``  — expired, but the last attempt failed recently or the provider asked
  us to wait (``Retry-After``); no upstream request is made until it ends.
* ``refreshing`` — another worker holds the refresh lock for this player.

Outcomes returned to callers use the spec §9.2 vocabulary: ``fresh``, ``partial``
(refresh succeeded but some resources failed), ``stale`` (served from last known
good data after a failed or skipped refresh). ``unavailable`` is raised as
:class:`DatasetUnavailableError` when there is no usable data at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.models import CacheMetadata


class Freshness(StrEnum):
    MISSING = "missing"
    FRESH = "fresh"
    EXPIRED = "expired"
    COOLDOWN = "cooldown"


class DataStatus(StrEnum):
    FRESH = "fresh"
    PARTIAL = "partial"
    STALE = "stale"


def classify(state: CacheMetadata | None, now: datetime) -> Freshness:
    """Freshness of a dataset at ``now``."""
    if state is None or state.last_success_at is None:
        if state is not None and _cooling_down(state, now):
            return Freshness.COOLDOWN
        return Freshness.MISSING
    if state.expires_at is not None and now < state.expires_at:
        return Freshness.FRESH
    if _cooling_down(state, now):
        return Freshness.COOLDOWN
    return Freshness.EXPIRED


def _cooling_down(state: CacheMetadata, now: datetime) -> bool:
    return state.next_refresh_not_before is not None and now < state.next_refresh_not_before


@dataclass(frozen=True, slots=True)
class DatasetStatus:
    """Freshness metadata to expose with every response built from the dataset."""

    username: str
    player_id: int
    data_status: DataStatus
    last_successful_update: datetime
    expires_at: datetime | None
    # Number of eligible games in the last successful refresh; 0 = confirmed empty.
    eligible_games: int | None
    # True when this call contacted the provider.
    refreshed: bool
    # Why the data is stale or partial (provider error code or REFRESH_IN_PROGRESS).
    refresh_error: str | None = None
    # Seconds until a new refresh may be attempted, when known.
    retry_after_seconds: float | None = None


class DatasetUnavailableError(Exception):
    """No usable cached data exists and a refresh did not (or could not) succeed."""

    def __init__(self, code: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.retry_after_seconds = retry_after_seconds
