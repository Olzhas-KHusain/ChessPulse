"""Accuracy math and UCI output parsing (pure, no engine, no database)."""

from __future__ import annotations

import pytest

from app.engine.accuracy import (
    BLUNDER,
    GOOD,
    INACCURACY,
    MISTAKE,
    centipawn_loss,
    classify,
    move_accuracy,
    win_percent,
)
from app.engine.uci import parse_identity, parse_info


def test_win_percent_is_symmetric_and_bounded() -> None:
    assert win_percent(0) == pytest.approx(50.0)
    assert win_percent(100) == pytest.approx(100 - win_percent(-100))
    # Scores are capped at ±1000 cp, so the curve never reaches exactly 0 or 100.
    assert win_percent(100_000) == win_percent(1_000)
    assert 0.0 < win_percent(-100_000) < 50.0 < win_percent(100_000) < 100.0


def test_win_percent_is_monotonic() -> None:
    values = [win_percent(cp) for cp in (-800, -200, 0, 200, 800)]
    assert values == sorted(values)


def test_perfect_move_scores_100() -> None:
    assert move_accuracy(50.0, 50.0) == 100.0


def test_accuracy_never_negative_even_for_a_collapse() -> None:
    assert move_accuracy(99.0, 0.0) == 0.0


def test_accuracy_decreases_with_lost_win_probability() -> None:
    small = move_accuracy(60.0, 58.0)
    large = move_accuracy(60.0, 30.0)
    assert 0.0 < large < small < 100.0


def test_centipawn_loss_is_clamped_and_never_negative() -> None:
    assert centipawn_loss(20, 20) == 0
    assert centipawn_loss(20, 120) == 0  # the move improved the position
    assert centipawn_loss(120, 20) == 100
    assert centipawn_loss(10_000, -10_000) == 1000


@pytest.mark.parametrize(
    ("loss", "best", "expected"),
    [
        (0, True, "best"),
        (0, False, GOOD),
        (49, False, GOOD),
        (50, False, INACCURACY),
        (99, False, INACCURACY),
        (100, False, MISTAKE),
        (199, False, MISTAKE),
        (200, False, BLUNDER),
        (1000, False, BLUNDER),
    ],
)
def test_classification_thresholds(loss: int, best: bool, expected: str) -> None:
    assert classify(loss, played_best_move=best) == expected


def test_parse_info_reads_centipawns_and_pv() -> None:
    line = (
        "info depth 12 seldepth 15 multipv 1 score cp 27 nodes 43275 "
        "nps 263871 hashfull 4 tbhits 0 time 164 pv e2e4 c7c5 g1f3"
    )
    assert parse_info(line) == (27, None, "e2e4")


def test_parse_info_reads_mate() -> None:
    assert parse_info("info depth 20 score mate -3 pv h5f7") == (None, -3, "h5f7")


def test_parse_info_ignores_lines_without_score() -> None:
    assert parse_info("info depth 1 currmove e2e4") == (None, None, None)


def test_parse_identity_splits_name_and_version() -> None:
    identity = parse_identity("id name Stockfish 19")
    assert identity is not None
    assert (identity.name, identity.version) == ("Stockfish", "19")


def test_parse_identity_handles_missing_version() -> None:
    identity = parse_identity("id name Stockfish")
    assert identity is not None
    assert (identity.name, identity.version) == ("Stockfish", "unknown")


def test_parse_identity_ignores_other_lines() -> None:
    assert parse_identity("id author the Stockfish developers") is None
