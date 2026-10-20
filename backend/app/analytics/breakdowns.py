"""Pure rating-history, opening and opponent breakdowns (spec §6.6-6.8).

All groups reuse :func:`app.analytics.overview.win_rate` and the same outcome rules as
the overview. Input rows are already restricted to the shared window and Rapid scope.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.analytics.overview import win_rate
from app.models.enums import PlayerColor, PlayerResult

UNKNOWN_OPENING_NAME = "Unknown"


@dataclass(frozen=True, slots=True)
class GameRow:
    """One eligible game from the searched player's perspective."""

    game_id: int
    played_at: datetime
    color: PlayerColor
    result: PlayerResult
    player_rating: int | None  # rating reported with the game for the searched player
    opponent_id: int
    opponent_username: str
    opponent_rating: int | None
    opening_key: str | None  # provider opening identifier; None = unknown
    opening_name: str | None
    eco_code: str | None


# --- outcome counting ---------------------------------------------------------------


@dataclass
class OutcomeCounts:
    games_count: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    unknown_results: int = 0

    def add(self, result: PlayerResult) -> None:
        self.games_count += 1
        if result is PlayerResult.WIN:
            self.wins += 1
        elif result is PlayerResult.LOSS:
            self.losses += 1
        elif result is PlayerResult.DRAW:
            self.draws += 1
        else:
            self.unknown_results += 1

    @property
    def win_rate(self) -> float | None:
        return win_rate(self.wins, self.losses, self.draws)


# --- rating history -----------------------------------------------------------------


class Coverage(StrEnum):
    COMPLETE = "complete"  # every game in scope produced an observation, dataset complete
    PARTIAL = "partial"  # some games lack a rating or the dataset is incomplete
    NONE = "none"  # no observation available


@dataclass(frozen=True, slots=True)
class RatingObservation:
    timestamp: datetime
    rating: int
    game_id: int
    source: str = "game_record"


@dataclass(frozen=True, slots=True)
class RatingHistory:
    points: tuple[RatingObservation, ...]
    games_considered: int
    games_without_rating: int
    duplicates_removed: int
    coverage: Coverage


def rating_history(rows: Iterable[GameRow], *, dataset_complete: bool) -> RatingHistory:
    """Observations from game records only, oldest first. No interpolation, no daily
    filling. Identical ``(timestamp, rating)`` observations are reported once."""
    ordered = sorted(rows, key=lambda r: (r.played_at, r.game_id))
    seen: set[tuple[datetime, int]] = set()
    points: list[RatingObservation] = []
    missing = duplicates = 0
    for row in ordered:
        if row.player_rating is None:
            missing += 1
            continue
        key = (row.played_at, row.player_rating)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        points.append(RatingObservation(row.played_at, row.player_rating, row.game_id))
    if not points:
        coverage = Coverage.NONE
    elif missing or not dataset_complete:
        coverage = Coverage.PARTIAL
    else:
        coverage = Coverage.COMPLETE
    return RatingHistory(tuple(points), len(ordered), missing, duplicates, coverage)


# --- grouping -----------------------------------------------------------------------


@dataclass
class OpeningGroup:
    key: str | None
    name: str
    eco_code: str | None
    counts: OutcomeCounts = field(default_factory=OutcomeCounts)

    @property
    def is_unknown(self) -> bool:
        return self.key is None


@dataclass
class OpponentGroup:
    opponent_id: int
    username: str
    counts: OutcomeCounts = field(default_factory=OutcomeCounts)
    last_played_at: datetime | None = None
    last_rating: int | None = None  # opponent's rating reported in the latest game
    _last_key: tuple[datetime, int] | None = None


def group_openings(rows: Iterable[GameRow]) -> list[OpeningGroup]:
    """Group by provider opening identifier; games without one form one Unknown group."""
    groups: dict[str | None, OpeningGroup] = {}
    for row in rows:
        group = groups.get(row.opening_key)
        if group is None:
            group = OpeningGroup(
                key=row.opening_key,
                name=(row.opening_name or row.opening_key)
                if row.opening_key
                else UNKNOWN_OPENING_NAME,
                eco_code=row.eco_code if row.opening_key else None,
            )
            groups[row.opening_key] = group
        group.counts.add(row.result)
    return list(groups.values())


def group_opponents(rows: Iterable[GameRow]) -> list[OpponentGroup]:
    """Group by the opponent's stable internal player id (one per provider account),
    never by display-name similarity."""
    groups: dict[int, OpponentGroup] = {}
    for row in rows:
        group = groups.setdefault(
            row.opponent_id, OpponentGroup(row.opponent_id, row.opponent_username)
        )
        group.counts.add(row.result)
        key = (row.played_at, row.game_id)
        if group._last_key is None or key > group._last_key:
            group._last_key = key
            group.last_played_at = row.played_at
            group.last_rating = row.opponent_rating
    return list(groups.values())


# --- sorting ------------------------------------------------------------------------


class GroupSort(StrEnum):
    GAMES = "games"  # games_count desc
    WIN_RATE = "win_rate"  # win_rate desc, null last
    NAME = "name"  # name / username asc


def sort_groups[G: (OpeningGroup, OpponentGroup)](
    groups: Sequence[G], sort: GroupSort, name: Callable[[G], str]
) -> list[G]:
    """Deterministic ordering; ties always fall back to name, then identifier."""

    def ident(g: G) -> str:
        return str(g.key) if isinstance(g, OpeningGroup) else str(g.opponent_id)

    if sort is GroupSort.GAMES:
        return sorted(groups, key=lambda g: (-g.counts.games_count, name(g), ident(g)))
    if sort is GroupSort.WIN_RATE:
        return sorted(
            groups,
            key=lambda g: (
                g.counts.win_rate is None,
                -(g.counts.win_rate or 0.0),
                -g.counts.games_count,
                name(g),
                ident(g),
            ),
        )
    return sorted(groups, key=lambda g: (name(g).lower(), ident(g)))
