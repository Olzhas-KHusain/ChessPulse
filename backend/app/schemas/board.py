"""API contract for the free analysis board."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

BoardStatus = Literal[
    "ongoing",
    "checkmate",
    "stalemate",
    "insufficient_material",
    "seventyfive_moves",
    "fivefold_repetition",
]
MoveClassification = Literal["best", "good", "inaccuracy", "mistake", "blunder"]
Side = Literal["white", "black"]


class BoardEvaluateRequest(BaseModel):
    fen: str = Field(min_length=1, max_length=128, description="Position in FEN notation.")


class BoardMoveRequest(BaseModel):
    fen: str = Field(min_length=1, max_length=128, description="Position before the move.")
    move_uci: str = Field(min_length=4, max_length=5, description="Legal move in UCI notation.")


class BoardEngineOut(BaseModel):
    name: str
    version: str
    depth: int


class BoardEvaluateResponse(BaseModel):
    """One position, evaluated from White's perspective."""

    fen: str
    turn: Side
    status: BoardStatus
    eval_cp: int = Field(description="Centipawns from White's perspective; mates use ±10000.")
    mate: int | None = Field(
        description="Mate distance from White's perspective; positive means White mates."
    )
    best_move_uci: str | None
    best_move_san: str | None
    engine: BoardEngineOut


class BoardMoveResponse(BaseModel):
    """A played move with the engine verdict for the position before and after it."""

    fen_before: str
    fen_after: str
    turn: Side = Field(description="The side that played the move.")
    move_number: int
    san: str
    uci: str
    eval_before_cp: int
    eval_after_cp: int
    mate_after: int | None
    cp_loss: int = Field(description="Centipawn loss from the mover's perspective, capped at 1000.")
    classification: MoveClassification
    best_move_uci: str | None
    best_move_san: str | None
    best_move_after_uci: str | None
    best_move_after_san: str | None
    status_after: BoardStatus
    engine: BoardEngineOut
