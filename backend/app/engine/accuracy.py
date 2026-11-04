"""Documented, deterministic accuracy math for engine analysis.

Everything here is a pure function of engine centipawn scores, so results are
reproducible and unit-testable without Stockfish.

Definitions (also surfaced in the API docs and the UI):

* **Win probability** converts centipawns to an expected score with the logistic
  curve used by Lichess (``50 + 50 * (2 / (1 + exp(-0.00368208 * cp)) - 1)``).
  Scores are capped at ±1000 cp so a single mate score cannot dominate.
* **Per-move accuracy** is the share of the mover's win probability that the move
  preserved: ``103.1668 * exp(-0.04354 * delta) - 3.1669``, clipped to 0–100,
  where ``delta = win% before - win% after`` (both from the mover's side). This is
  the published Lichess formula, not a ChessPulse invention.
* **Game accuracy** is the arithmetic mean of the player's per-move accuracies.
  It is not weighted by position difficulty; a game with many trivial moves and
  one blunder therefore scores higher than a sharp game with the same blunder.
  The UI says "mean move accuracy" to avoid overclaiming.
* **Centipawn loss (CPL)** is ``max(0, eval before - eval after)`` from the
  mover's side, capped at 1000. **ACPL** is its arithmetic mean over the player's
  moves.
* **Move labels** are purely CPL thresholds: ``best`` (played the engine's top
  move), ``good`` (<50), ``inaccuracy`` (50–99), ``mistake`` (100–199),
  ``blunder`` (≥200). They are engine-derived; no label is assigned without an
  engine score.
"""

from __future__ import annotations

import math

WIN_PERCENT_CAP_CP = 1_000
CPL_CAP = 1_000

BEST = "best"
GOOD = "good"
INACCURACY = "inaccuracy"
MISTAKE = "mistake"
BLUNDER = "blunder"

CLASSIFICATIONS = (BEST, GOOD, INACCURACY, MISTAKE, BLUNDER)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def win_percent(cp: int | float) -> float:
    """Expected score in percent (0–100) for the side the score belongs to."""
    bounded = clamp(cp, -WIN_PERCENT_CAP_CP, WIN_PERCENT_CAP_CP)
    return 50.0 + 50.0 * (2.0 / (1.0 + math.exp(-0.00368208 * bounded)) - 1.0)


def move_accuracy(win_before: float, win_after: float) -> float:
    """Accuracy of one move, given the mover's win% before and after it."""
    delta = max(0.0, win_before - win_after)
    raw = 103.1668 * math.exp(-0.04354 * delta) - 3.1669
    return round(clamp(raw, 0.0, 100.0), 2)


def centipawn_loss(eval_before: int, eval_after: int) -> int:
    """Loss in centipawns from the mover's perspective, capped at 1000."""
    return int(clamp(eval_before - eval_after, 0, CPL_CAP))


def classify(cp_loss: int, *, played_best_move: bool) -> str:
    """Label a move from its centipawn loss and whether it matched the engine."""
    if played_best_move:
        return BEST
    if cp_loss < 50:
        return GOOD
    if cp_loss < 100:
        return INACCURACY
    if cp_loss < 200:
        return MISTAKE
    return BLUNDER


def mean(values: list[float] | list[int]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None
