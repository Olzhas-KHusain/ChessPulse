"""Per-game analysis with a deterministic fake engine (no Stockfish, no database)."""

from __future__ import annotations

import chess
import pytest

from app.engine.game import AnalysisError, analyse_game
from app.engine.uci import EngineIdentity, Evaluation

PGN_CLEAN = '[White "A"]\n[Black "B"]\n[Result "1-0"]\n\n1. e4 e5 2. Nf3 Nc6 1-0\n'
PGN_MATE = '[White "A"]\n[Black "B"]\n[Result "0-1"]\n\n1. f3 e5 2. g4 Qh4# 0-1\n'


class FakeEngine:
    identity = EngineIdentity("Fake", "1.0")
    depth = 12

    def __init__(self, evaluations: dict[str, Evaluation]) -> None:
        self._evaluations = evaluations
        self.calls: list[str] = []

    def evaluate(self, fen: str) -> Evaluation:
        self.calls.append(fen)
        return self._evaluations[fen]


def _positions(sans: list[str]) -> list[str]:
    board = chess.Board()
    fens = [board.fen()]
    for san in sans:
        board.push_san(san)
        fens.append(board.fen())
    return fens


def test_all_best_moves_score_100_accuracy() -> None:
    fens = _positions(["e4", "e5", "Nf3", "Nc6"])
    engine = FakeEngine(
        {
            fens[0]: Evaluation(cp=20, mate=None, best_move="e2e4"),
            fens[1]: Evaluation(cp=-30, mate=None, best_move="e7e5"),
            fens[2]: Evaluation(cp=25, mate=None, best_move="g1f3"),
            fens[3]: Evaluation(cp=-40, mate=None, best_move="b8c6"),
            fens[4]: Evaluation(cp=35, mate=None, best_move="f1c4"),
        }
    )

    payload = analyse_game(PGN_CLEAN, engine)

    assert payload["schema_version"] == 1
    assert payload["engine"] == {"name": "Fake", "version": "1.0", "depth": 12}
    assert payload["result"] == "1-0"
    assert [move["san"] for move in payload["moves"]] == ["e4", "e5", "Nf3", "Nc6"]
    assert [move["classification"] for move in payload["moves"]] == ["best"] * 4
    assert all(move["cp_loss"] == 0 for move in payload["moves"])
    assert payload["summary"]["white"]["accuracy"] == 100.0
    assert payload["summary"]["black"]["accuracy"] == 100.0
    assert payload["summary"]["white"]["acpl"] == 0
    assert payload["summary"]["white"]["moves"] == 2
    # Five positions, each evaluated once.
    assert len(engine.calls) == 5


def test_blunders_are_classified_from_engine_scores() -> None:
    fens = _positions(["f3", "e5", "g4", "Qh4#"])
    engine = FakeEngine(
        {
            fens[0]: Evaluation(cp=0, mate=None, best_move="e2e4"),
            fens[1]: Evaluation(cp=100, mate=None, best_move="e7e5"),
            fens[2]: Evaluation(cp=-100, mate=None, best_move="g2g3"),
            fens[3]: Evaluation(cp=350, mate=None, best_move="d8h4"),
        }
    )

    payload = analyse_game(PGN_MATE, engine)
    moves = payload["moves"]

    assert [move["classification"] for move in moves] == ["mistake", "best", "blunder", "best"]
    assert moves[0]["cp_loss"] == 100
    assert moves[2]["cp_loss"] == 250
    assert moves[3]["eval_cp"] == -10_000  # terminal checkmate, White is mated
    assert payload["summary"]["white"]["counts"] == {
        "best": 0,
        "good": 0,
        "inaccuracy": 0,
        "mistake": 1,
        "blunder": 1,
    }
    assert payload["summary"]["black"]["accuracy"] == 100.0


def test_engine_mate_score_is_mapped_to_a_large_centipawn_value() -> None:
    fens = _positions(["e4"])
    engine = FakeEngine(
        {
            fens[0]: Evaluation(cp=None, mate=2, best_move="e2e4"),
            fens[1]: Evaluation(cp=30, mate=None, best_move="e7e5"),
        }
    )
    payload = analyse_game('[White "A"]\n[Black "B"]\n\n1. e4 1-0\n', engine)
    assert payload["moves"][0]["eval_before_cp"] == 10_000
    assert payload["moves"][0]["eval_cp"] == -30


@pytest.mark.parametrize(
    ("pgn", "code"),
    [
        (None, "missing_pgn"),
        ("   ", "missing_pgn"),
        ("1. e4 e5 2. Ke3 1-0", "malformed_pgn"),
        ('[White "A"]\n\n', "no_moves"),
    ],
)
def test_unusable_games_raise_specific_codes(pgn: str | None, code: str) -> None:
    with pytest.raises(AnalysisError) as error:
        analyse_game(pgn, FakeEngine({}))
    assert error.value.code == code
