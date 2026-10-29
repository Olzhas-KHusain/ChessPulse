"""API contract for the cross-game form report."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.overview import Period

LeakKind = Literal["phase", "color", "opening"]
Phase = Literal["opening", "middlegame", "late"]


class FormAccuracyPoint(BaseModel):
    game_id: str
    played_at: datetime
    color: Literal["white", "black"]
    result: str
    opponent: str
    accuracy: float | None
    acpl: float | None
    blunders: int
    mistakes: int


class FormGroup(BaseModel):
    """One slice of the player's moves (a phase, a colour or an opening)."""

    key: str
    label: str
    games: int
    moves: int
    blunders: int
    mistakes: int
    inaccuracies: int
    acpl: float | None
    accuracy: float | None
    # Percentage points of win probability given up per analysed game in this slice.
    wp_loss_per_game: float


class FormMoment(BaseModel):
    game_id: str
    played_at: datetime
    color: Literal["white", "black"]
    opponent: str
    move_number: int
    san: str
    classification: Literal["best", "good", "inaccuracy", "mistake", "blunder"]
    cp_loss: int
    wp_loss: float
    phase: Phase
    opening_name: str | None
    game_url: str | None


class FormLeak(BaseModel):
    kind: LeakKind
    label: str
    wp_loss_per_game: float
    games: int
    moves: int
    blunders: int
    mistakes: int


class FormReportResponse(BaseModel):
    """Aggregates over every analysed game in the current scope.

    ``games_total`` is the number of eligible games; ``games_analyzed`` is how many of
    them have a stored analysis for the current engine profile. The report is still
    meaningful while some games are pending, but the UI says so.
    """

    username: str
    period: Period
    time_class: str
    data_status: str
    refresh_error: str | None = None
    as_of: datetime
    last_successful_update: datetime | None = None

    games_total: int
    games_analyzed: int
    games_queued: int
    games_running: int
    games_failed: int

    accuracy_mean: float | None = Field(description="Mean per-game accuracy of the player.")
    opponent_accuracy_mean: float | None
    acpl_mean: float | None
    wp_loss_per_game: float | None = Field(
        description="Win probability points given up per analysed game, own moves only."
    )

    accuracy_trend: list[FormAccuracyPoint]
    by_phase: list[FormGroup]
    by_color: list[FormGroup]
    by_opening: list[FormGroup]
    top_moments: list[FormMoment]
    primary_leak: FormLeak | None


class AnalyzeScopeResponse(BaseModel):
    """Result of queueing every missing analysis in the scope."""

    username: str
    time_class: str
    games_total: int
    already_analyzed: int
    queued: int
    pending: int
