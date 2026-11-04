"""Pure overview calculations (spec §6.4-6.5). No I/O; deterministic for equal input.

Conventions:

* ``games_count`` counts every eligible game, including results that could not be
  classified (``unknown_results``). Outcome counts and the win rate use confirmed
  wins, losses and draws only.
* ``win_rate = wins / (wins + losses + draws) * 100``, rounded half-up to 2 decimals;
  ``None`` when the denominator is 0.
* Games are ordered by ``(played_at, game_id)`` ascending: the internal id breaks
  equal timestamps deterministically.
* Streaks: a win extends a winning streak; a loss or a draw ends it. An unknown result
  also ends every streak, because it might have been a loss; in that case
  ``streak_may_be_incomplete`` is true. The current streak is the run of identical
  outcomes ending at the latest game; it is ``None`` when there are no games or the
  latest result is unknown.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from app.models.enums import PlayerResult


@dataclass(frozen=True, slots=True)
class GameOutcome:
    played_at: datetime
    game_id: int
    result: PlayerResult


@dataclass(frozen=True, slots=True)
class Streak:
    type: PlayerResult  # win, loss or draw (never unknown)
    length: int


@dataclass(frozen=True, slots=True)
class OverviewMetrics:
    games_count: int
    wins: int
    losses: int
    draws: int
    unknown_results: int
    win_rate: float | None
    current_streak: Streak | None
    longest_winning_streak: int | None
    streak_may_be_incomplete: bool


def win_rate(wins: int, losses: int, draws: int) -> float | None:
    decided = wins + losses + draws
    if decided == 0:
        return None
    value = Decimal(wins) * 100 / Decimal(decided)
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def chronological(outcomes: Iterable[GameOutcome]) -> list[GameOutcome]:
    return sorted(outcomes, key=lambda o: (o.played_at, o.game_id))


def current_streak(ordered: list[GameOutcome]) -> Streak | None:
    if not ordered or ordered[-1].result is PlayerResult.UNKNOWN:
        return None
    kind = ordered[-1].result
    length = 0
    for outcome in reversed(ordered):
        if outcome.result is not kind:
            break
        length += 1
    return Streak(type=kind, length=length)


def longest_winning_streak(ordered: list[GameOutcome]) -> int | None:
    if not ordered:
        return None
    best = run = 0
    for outcome in ordered:
        run = run + 1 if outcome.result is PlayerResult.WIN else 0
        best = max(best, run)
    return best


def compute_overview(outcomes: Iterable[GameOutcome], *, dataset_complete: bool) -> OverviewMetrics:
    ordered = chronological(outcomes)
    counts = {result: 0 for result in PlayerResult}
    for outcome in ordered:
        counts[outcome.result] += 1
    wins, losses, draws = (
        counts[PlayerResult.WIN],
        counts[PlayerResult.LOSS],
        counts[PlayerResult.DRAW],
    )
    unknown = counts[PlayerResult.UNKNOWN]
    return OverviewMetrics(
        games_count=len(ordered),
        wins=wins,
        losses=losses,
        draws=draws,
        unknown_results=unknown,
        win_rate=win_rate(wins, losses, draws),
        current_streak=current_streak(ordered),
        longest_winning_streak=longest_winning_streak(ordered),
        streak_may_be_incomplete=bool(ordered) and (unknown > 0 or not dataset_complete),
    )
