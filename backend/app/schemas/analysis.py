"""API contract for engine analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AnalysisStatus = Literal["missing", "queued", "running", "completed", "failed"]


class AnalysisMove(BaseModel):
    """One ply with the engine verdict for the position before it."""

    ply: int
    move_number: int
    color: Literal["white", "black"]
    san: str
    uci: str
    # Evaluations from White's perspective (centipawns): before and after the move.
    eval_before_cp: int
    eval_cp: int
    mate: int | None
    best_move_uci: str | None
    best_move_san: str | None
    cp_loss: int
    classification: Literal["best", "good", "inaccuracy", "mistake", "blunder"]


class PlayerAnalysisSummary(BaseModel):
    accuracy: float | None = Field(description="Mean per-move accuracy, 0-100.")
    acpl: float | None = Field(description="Average centipawn loss per move.")
    moves: int
    counts: dict[str, int]


class AnalysisEngine(BaseModel):
    name: str
    version: str
    depth: int


class AnalysisPayload(BaseModel):
    schema_version: int
    engine: AnalysisEngine
    players: dict[str, str]
    result: str
    moves: list[AnalysisMove]
    summary: dict[str, PlayerAnalysisSummary]


class AnalysisStateResponse(BaseModel):
    """Current state of one game's analysis; ``analysis`` is set only when done."""

    username: str
    game_id: str
    status: AnalysisStatus
    error_code: str | None = None
    requested_at: datetime | None = None
    completed_at: datetime | None = None
    analysis: AnalysisPayload | None = None
