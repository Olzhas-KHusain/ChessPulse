"""Free-board engine math: FEN validation, evaluation and move classification."""

from __future__ import annotations

import pytest

from app.engine.board import (
    IllegalMoveError,
    InvalidFenError,
    analyze_move,
    evaluate_fen,
    parse_fen,
)
from app.engine.game import Engine
from app.engine.uci import EngineIdentity, Evaluation

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


class ScriptedEngine:
    identity = EngineIdentity("Fake", "1.0")
    depth = 10

    def __init__(self, evaluations: list[Evaluation]) -> None:
        self._evaluations = iter(evaluations)
        self.calls = 0

    def evaluate(self, fen: str) -> Evaluation:
        self.calls += 1
        return next(self._evaluations)


class NoEngine:
    identity = EngineIdentity("Fake", "1.0")
    depth = 10

    def evaluate(self, fen: str) -> Evaluation:  # pragma: no cover - must not be called
        raise AssertionError(f"engine must not be called for {fen}")


def test_evaluate_start_position_uses_white_perspective() -> None:
    engine = ScriptedEngine([Evaluation(cp=35, mate=None, best_move="e2e4")])
    result = evaluate_fen(START, engine)

    assert result.fen == START
    assert result.turn == "white"
    assert result.status == "ongoing"
    assert result.eval_cp == 35
    assert result.mate is None
    assert result.best_move_uci == "e2e4"
    assert result.best_move_san == "e4"


def test_black_to_move_score_is_negated() -> None:
    engine = ScriptedEngine([Evaluation(cp=50, mate=None, best_move="e7e5")])
    result = evaluate_fen(AFTER_E4, engine)

    assert result.turn == "black"
    assert result.eval_cp == -50  # engine speaks for the side to move; API speaks for White
    assert result.best_move_san == "e5"


def test_analyze_move_classifies_from_the_movers_side() -> None:
    engine = ScriptedEngine(
        [
            Evaluation(cp=20, mate=None, best_move="d2d4"),  # before: White slightly better
            Evaluation(cp=300, mate=None, best_move="e7e5"),  # after: Black is much better
        ]
    )
    result = analyze_move(START, "e2e4", engine)

    assert result.san == "e4"
    assert result.uci == "e2e4"
    assert result.turn == "white"
    assert result.move_number == 1
    assert result.fen_before == START
    assert result.fen_after == AFTER_E4
    assert result.eval_before_cp == 20
    assert result.eval_after_cp == -300
    assert result.cp_loss == 320
    assert result.classification == "blunder"
    assert result.best_move_san == "d4"
    assert result.best_move_after_san == "e5"


def test_played_best_move_is_always_best() -> None:
    engine = ScriptedEngine(
        [
            Evaluation(cp=20, mate=None, best_move="e2e4"),
            Evaluation(cp=20, mate=None, best_move="e7e5"),  # Black is better after e4
        ]
    )
    result = analyze_move(START, "e2e4", engine)

    assert result.cp_loss == 40
    assert result.classification == "best"


def test_illegal_move_is_rejected_without_an_engine_call() -> None:
    with pytest.raises(IllegalMoveError):
        analyze_move(START, "e2e5", NoEngine())


@pytest.mark.parametrize("uci", ["", "e2", "e2e9", "not-a-move"])
def test_malformed_uci_is_rejected(uci: str) -> None:
    with pytest.raises(IllegalMoveError):
        analyze_move(START, uci, NoEngine())


@pytest.mark.parametrize(
    "fen",
    [
        "not a fen",
        "8/8/8/8/8/8/8/8 w - - 0 1",  # no kings
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR x KQkq - 0 1",  # bad side to move
    ],
)
def test_invalid_fen_is_rejected(fen: str) -> None:
    with pytest.raises(InvalidFenError):
        parse_fen(fen)


def test_checkmate_needs_no_engine_search() -> None:
    result = evaluate_fen("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1", NoEngine())

    assert result.status == "checkmate"
    assert result.eval_cp == 10_000  # Black is mated, so White is winning
    assert result.best_move_uci is None


def test_stalemate_is_a_zero_evaluation() -> None:
    result = evaluate_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1", NoEngine())

    assert result.status == "stalemate"
    assert result.eval_cp == 0
    assert result.best_move_uci is None


def test_engine_protocol_is_satisfied_by_the_scripted_engine() -> None:
    engine: Engine = ScriptedEngine([Evaluation(cp=0, mate=None, best_move=None)])
    assert engine.depth == 10
