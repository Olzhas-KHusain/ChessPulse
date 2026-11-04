"""Pure overview analytics: counts, win rate, streaks (no database, no network)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.analytics.overview import GameOutcome, Streak, compute_overview, win_rate
from app.models import PlayerResult

W, L, D, U = PlayerResult.WIN, PlayerResult.LOSS, PlayerResult.DRAW, PlayerResult.UNKNOWN
T0 = datetime(2026, 10, 1, tzinfo=UTC)


def seq(*results: PlayerResult) -> list[GameOutcome]:
    """Outcomes one minute apart, in the given chronological order."""
    return [GameOutcome(T0 + timedelta(minutes=i), i + 1, r) for i, r in enumerate(results)]


def test_zero_games() -> None:
    m = compute_overview([], dataset_complete=True)
    assert (m.games_count, m.wins, m.losses, m.draws) == (0, 0, 0, 0)
    assert m.win_rate is None
    assert m.current_streak is None
    assert m.longest_winning_streak is None
    assert not m.streak_may_be_incomplete


@pytest.mark.parametrize(
    ("result", "counts", "rate", "longest"),
    [
        (W, (1, 0, 0), 100.0, 1),
        (L, (0, 1, 0), 0.0, 0),
        (D, (0, 0, 1), 0.0, 0),
    ],
)
def test_single_game(
    result: PlayerResult, counts: tuple[int, int, int], rate: float, longest: int
) -> None:
    m = compute_overview(seq(result), dataset_complete=True)
    assert (m.wins, m.losses, m.draws) == counts
    assert m.win_rate == rate
    assert m.current_streak == Streak(result, 1)
    assert m.longest_winning_streak == longest


def test_mixed_outcomes_and_draws_in_denominator() -> None:
    m = compute_overview(seq(W, L, D, W, W, L, W), dataset_complete=True)
    assert (m.games_count, m.wins, m.losses, m.draws) == (7, 4, 2, 1)
    assert m.win_rate == 57.14  # 4 / 7 * 100
    assert m.current_streak == Streak(W, 1)
    assert m.longest_winning_streak == 2


def test_consecutive_wins() -> None:
    m = compute_overview(seq(L, W, W, W), dataset_complete=True)
    assert m.current_streak == Streak(W, 3)
    assert m.longest_winning_streak == 3


def test_draw_breaks_a_winning_streak() -> None:
    m = compute_overview(seq(W, W, D, W), dataset_complete=True)
    assert m.longest_winning_streak == 2
    assert m.current_streak == Streak(W, 1)


def test_current_losing_streak() -> None:
    assert compute_overview(seq(W, L, L), dataset_complete=True).current_streak == Streak(L, 2)


def test_equal_timestamps_are_ordered_by_game_id() -> None:
    same = T0
    outcomes = [GameOutcome(same, 2, L), GameOutcome(same, 1, W), GameOutcome(same, 3, W)]
    m = compute_overview(outcomes, dataset_complete=True)
    # Order: id1 W, id2 L, id3 W regardless of input order.
    assert m.current_streak == Streak(W, 1)
    assert m.longest_winning_streak == 1
    assert compute_overview(list(reversed(outcomes)), dataset_complete=True) == m


def test_unknown_result_is_excluded_from_rate_and_breaks_streaks() -> None:
    m = compute_overview(seq(W, W, U, W), dataset_complete=True)
    assert (m.games_count, m.wins, m.unknown_results) == (4, 3, 1)
    assert m.win_rate == 100.0
    assert m.longest_winning_streak == 2  # never joined across an unknown
    assert m.streak_may_be_incomplete


def test_latest_unknown_means_no_current_streak() -> None:
    m = compute_overview(seq(W, U), dataset_complete=True)
    assert m.current_streak is None


def test_only_unknown_results_give_null_win_rate() -> None:
    m = compute_overview(seq(U, U), dataset_complete=True)
    assert m.games_count == 2
    assert m.win_rate is None


def test_partial_dataset_flags_streaks() -> None:
    assert compute_overview(seq(W), dataset_complete=False).streak_may_be_incomplete


@pytest.mark.parametrize(
    ("w", "l", "d", "expected"),
    [(1, 2, 0, 33.33), (2, 1, 0, 66.67), (1, 0, 7, 12.5), (1, 1, 6, 12.5), (0, 0, 0, None)],
)
def test_win_rate_rounding(w: int, l: int, d: int, expected: float | None) -> None:  # noqa: E741
    assert win_rate(w, l, d) == expected
