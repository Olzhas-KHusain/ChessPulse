"""Per-game engine analysis: PGN -> per-ply evaluations -> summary payload.

The payload is a plain JSON-serializable document with a versioned schema. It is
what the worker stores in ``game_analysis.payload`` and what the API returns, so
the contract is defined here once.

Honesty rules:

* every number comes from engine scores; nothing is estimated from results;
* the engine identity, depth and options are recorded next to the numbers;
* mate scores are recorded as ``mate`` and mapped to ±10000 cp for arithmetic;
* no "estimated Elo" is produced — accuracy does not identify a rating.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Protocol

import chess
import chess.pgn

from app.engine.accuracy import (
    CLASSIFICATIONS,
    centipawn_loss,
    classify,
    mean,
    move_accuracy,
    win_percent,
)
from app.engine.uci import EngineIdentity, Evaluation

SCHEMA_VERSION = 1
MAX_ANALYSED_PLIES = 400
MATE_CP = 10_000


class AnalysisError(RuntimeError):
    """A game cannot be analysed; ``code`` is a short, safe machine code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class Engine(Protocol):
    """The subset of the UCI client used by :func:`analyse_game`."""

    @property
    def identity(self) -> EngineIdentity: ...

    @property
    def depth(self) -> int: ...

    def evaluate(self, fen: str) -> Evaluation: ...


@dataclass(frozen=True, slots=True)
class _PositionEval:
    cp: int | None  # White's perspective; None only for an engine mate score
    mate: int | None  # White's perspective; positive = White mates
    best_move_uci: str | None


def _white_perspective(board: chess.Board, evaluation: Evaluation) -> _PositionEval:
    sign = 1 if board.turn == chess.WHITE else -1
    return _PositionEval(
        cp=None if evaluation.cp is None else sign * evaluation.cp,
        mate=None if evaluation.mate is None else sign * evaluation.mate,
        best_move_uci=evaluation.best_move,
    )


def _terminal_eval(board: chess.Board) -> _PositionEval | None:
    """Evaluations that need no engine call."""
    if board.is_checkmate():
        # The side to move is mated, so White is winning iff Black is to move.
        white_is_winning = board.turn == chess.BLACK
        return _PositionEval(
            cp=MATE_CP if white_is_winning else -MATE_CP,
            mate=None,
            best_move_uci=None,
        )
    if board.is_stalemate() or board.is_insufficient_material():
        return _PositionEval(cp=0, mate=None, best_move_uci=None)
    return None


def _evaluate(board: chess.Board, engine: Engine) -> _PositionEval:
    terminal = _terminal_eval(board)
    if terminal is not None:
        return terminal
    return _white_perspective(board, engine.evaluate(board.fen()))


def _score_cp(evaluation: _PositionEval) -> int:
    if evaluation.mate is not None:
        return MATE_CP if evaluation.mate > 0 else -MATE_CP
    return evaluation.cp or 0


def _best_move_san(board: chess.Board, uci: str | None) -> str | None:
    if not uci:
        return None
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        return None
    return board.san(move) if move in board.legal_moves else None


def analyse_game(
    pgn: str | None, engine: Engine, *, max_plies: int = MAX_ANALYSED_PLIES
) -> dict[str, Any]:
    """Analyse a PGN and return the versioned payload.

    Raises:
        AnalysisError: ``missing_pgn``, ``malformed_pgn``, ``no_moves`` or
            ``too_many_moves``. One bad game never affects another.
    """
    if pgn is None or not pgn.strip():
        raise AnalysisError("missing_pgn")

    try:
        game = chess.pgn.read_game(io.StringIO(pgn))
    except Exception:  # defensive: a parser bug must not crash the worker
        raise AnalysisError("malformed_pgn") from None
    if game is None:
        raise AnalysisError("malformed_pgn")
    if game.errors:
        raise AnalysisError("malformed_pgn")

    board = game.board()
    moves: list[chess.Move] = []
    for move in game.mainline_moves():
        if len(moves) >= max_plies:
            raise AnalysisError("too_many_moves")
        moves.append(move)
    if not moves:
        raise AnalysisError("no_moves")

    evaluations: list[_PositionEval] = []
    for index in range(len(moves) + 1):
        evaluations.append(_evaluate(board, engine))
        if index < len(moves):
            board.push(moves[index])

    identity = engine.identity
    san_board = game.board()
    rows: list[dict[str, Any]] = []
    accuracy: dict[str, list[float]] = {"white": [], "black": []}
    losses: dict[str, list[int]] = {"white": [], "black": []}
    counts: dict[str, dict[str, int]] = {
        "white": dict.fromkeys(CLASSIFICATIONS, 0),
        "black": dict.fromkeys(CLASSIFICATIONS, 0),
    }

    for index, move in enumerate(moves):
        before, after = evaluations[index], evaluations[index + 1]
        mover_is_white = index % 2 == 0
        color = "white" if mover_is_white else "black"
        sign = 1 if mover_is_white else -1

        before_cp = _score_cp(before) * sign
        after_cp = _score_cp(after) * sign
        loss = centipawn_loss(before_cp, after_cp)
        played_best = before.best_move_uci == move.uci()

        rows.append(
            {
                "ply": index + 1,
                "move_number": index // 2 + 1,
                "color": color,
                "san": san_board.san(move),
                "uci": move.uci(),
                "eval_before_cp": _score_cp(before),
                "eval_cp": _score_cp(after),
                "mate": after.mate,
                "best_move_uci": before.best_move_uci,
                "best_move_san": _best_move_san(san_board, before.best_move_uci),
                "cp_loss": loss,
                "classification": classify(loss, played_best_move=played_best),
            }
        )
        san_board.push(move)
        accuracy[color].append(move_accuracy(win_percent(before_cp), win_percent(after_cp)))
        losses[color].append(loss)
        counts[color][rows[-1]["classification"]] += 1

    summary = {
        color: {
            "accuracy": mean(accuracy[color]),
            "acpl": mean(losses[color]),
            "moves": len(accuracy[color]),
            "counts": counts[color],
        }
        for color in ("white", "black")
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "engine": {
            "name": identity.name,
            "version": identity.version,
            "depth": engine.depth,
        },
        "players": {
            "white": game.headers.get("White", ""),
            "black": game.headers.get("Black", ""),
        },
        "result": game.headers.get("Result", "*"),
        "moves": rows,
        "summary": summary,
    }
