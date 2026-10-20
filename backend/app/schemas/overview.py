"""Response schemas for ``GET /api/v1/players/{username}/overview`` and errors."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Period(BaseModel):
    start: datetime = Field(description="Window start, inclusive (UTC).")
    end: datetime = Field(description="Window end, exclusive (UTC).")
    timezone: Literal["UTC"] = "UTC"


class StreakOut(BaseModel):
    type: Literal["win", "loss", "draw"]
    length: int = Field(ge=1)


class CurrentRating(BaseModel):
    """The player's current Rapid rating from the provider's player statistics.

    Not derived from any game; per-game ratings are exposed by other endpoints."""

    rating: int
    as_of: datetime | None = Field(
        description="Provider timestamp of the last rated Rapid game behind this value."
    )
    source: Literal["provider_stats"] = "provider_stats"


class OverviewResponse(BaseModel):
    username: str
    period: Period
    games_count: int = Field(description="Eligible Rapid games in the period.")
    wins: int
    losses: int
    draws: int
    unknown_results: int = Field(
        description="Eligible games whose result could not be classified; not in win_rate."
    )
    win_rate: float | None = Field(
        description="wins / (wins + losses + draws) * 100, 2 decimals; null when no decided games."
    )
    current_rating: int | None = Field(description="Same value as current_rating_detail.rating.")
    current_rating_detail: CurrentRating | None
    current_streak: StreakOut | None
    longest_winning_streak: int | None
    streak_may_be_incomplete: bool = Field(
        description="True when unknown results or missing data may hide games."
    )
    data_status: Literal["fresh", "partial", "stale"]
    missing_sections: list[str]
    refresh_error: str | None = Field(
        description="Machine code explaining a partial or stale status, if any."
    )
    as_of: datetime = Field(description="Time this response was computed (UTC).")
    last_successful_update: datetime


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody
