"""Engine analysis for the free board: one arbitrary position or one legal move.

The free board is independent of the stored player dataset. It accepts a FEN and
returns the same engine verdicts that :mod:`app.engine.game` uses for games, so
the UI can show one consistent evaluation vocabulary everywhere.

All scores in this module are from White's perspective; ``mate`` is positive when
White is mating. ``cp_loss`` and ``classification`` are from the mover's side.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

import chess

from app.engine.accuracy import centipawn_loss, classify
from app.engine.game import (
    Engine,
    PositionEval,
    best_move_san,
    evaluate_board,
    score_cp,
)

MAX_FEN_LENGTH = 128
MAX_UCI_LENGTH = 5

BoardStatus = Literal[
    "ongoing",
    "checkmate",
    "stalemate",
    "insufficient_material",
    "seventyfive_moves",
    "fivefold_repetition",
]
MoveClassification = Literal["best", "good", "inaccuracy", "mistake", "blunder"]


class BoardError(ValueError):
    """A position or move cannot be analysed; ``code`` is safe to expose."""

    code = "BOARD_ERROR"
    message = "The position could not be analysed."


class InvalidFenError(BoardError):
    code = "INVALID_FEN"
    message = "The position is not a valid chess position."


class IllegalMoveError(BoardError):
    code = "ILLEGAL_MOVE"
    message = "That move is not legal in this position."


@dataclass(frozen=True, slots=True)
class BoardEvaluation:
    fen: str
    turn: Literal["white", "black"]
    status: BoardStatus
    eval_cp: int
    mate: int | None
    best_move_uci: str | None
    best_move_san: str | None


@dataclass(frozen=True, slots=True)
class MoveAnalysis:
    fen_before: str
    fen_after: str
    turn: Literal["white", "black"]
    move_number: int
    san: str
    uci: str
    eval_before_cp: int
    eval_after_cp: int
    mate_after: int | None
    cp_loss: int
    classification: MoveClassification
    best_move_uci: str | None
    best_move_san: str | None
    best_move_after_uci: str | None
    best_move_after_san: str | None
    status_after: BoardStatus


def parse_fen(fen: str) -> chess.Board:
    """Parse a FEN and reject positions Stockfish cannot safely analyse."""
    raw = fen.strip()
    if not 1 <= len(raw) <= MAX_FEN_LENGTH:
        raise InvalidFenError
    try:
        board = chess.Board(raw)
    except ValueError:
        raise InvalidFenError from None
    if not board.is_valid():
        raise InvalidFenError
    return board


def parse_move(board: chess.Board, uci: str) -> chess.Move:
    """Parse a UCI move and require it to be legal on ``board``."""
    raw = uci.strip()
    if not 4 <= len(raw) <= MAX_UCI_LENGTH:
        raise IllegalMoveError
    try:
        move = chess.Move.from_uci(raw)
    except ValueError:
        raise IllegalMoveError from None
    if move not in board.legal_moves:
        raise IllegalMoveError
    return move


def position_status(board: chess.Board) -> BoardStatus:
    if board.is_checkmate():
        return "checkmate"
    if board.is_stalemate():
        return "stalemate"
    if board.is_insufficient_material():
        return "insufficient_material"
    if board.is_seventyfive_moves():
        return "seventyfive_moves"
    if board.is_fivefold_repetition():
        return "fivefold_repetition"
    return "ongoing"


def _evaluation(board: chess.Board, verdict: PositionEval) -> BoardEvaluation:
    return BoardEvaluation(
        fen=board.fen(),
        turn="white" if board.turn == chess.WHITE else "black",
        status=position_status(board),
        eval_cp=score_cp(verdict),
        mate=verdict.mate,
        best_move_uci=verdict.best_move_uci,
        best_move_san=best_move_san(board, verdict.best_move_uci),
    )


def evaluate_fen(fen: str, engine: Engine) -> BoardEvaluation:
    """Evaluate one position. Terminal positions need no engine search."""
    board = parse_fen(fen)
    return _evaluation(board, evaluate_board(board, engine))


def analyze_move(fen: str, uci: str, engine: Engine) -> MoveAnalysis:
    """Evaluate a legal move and classify it from the mover's perspective."""
    board = parse_fen(fen)
    move = parse_move(board, uci)
    mover_is_white = board.turn == chess.WHITE
    before = _evaluation(board, evaluate_board(board, engine))
    move_number = board.fullmove_number
    san = board.san(move)
    board.push(move)
    after = _evaluation(board, evaluate_board(board, engine))

    sign = 1 if mover_is_white else -1
    loss = centipawn_loss(before.eval_cp * sign, after.eval_cp * sign)
    played_best = before.best_move_uci == move.uci()
    return MoveAnalysis(
        fen_before=before.fen,
        fen_after=after.fen,
        turn="white" if mover_is_white else "black",
        move_number=move_number,
        san=san,
        uci=move.uci(),
        eval_before_cp=before.eval_cp,
        eval_after_cp=after.eval_cp,
        mate_after=after.mate,
        cp_loss=loss,
        classification=cast(MoveClassification, classify(loss, played_best_move=played_best)),
        best_move_uci=before.best_move_uci,
        best_move_san=before.best_move_san,
        best_move_after_uci=after.best_move_uci,
        best_move_after_san=after.best_move_san,
        status_after=after.status,
    )
