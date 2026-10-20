"""Response schemas for rating-history, openings and opponents endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.overview import Period

DataStatusOut = Literal["fresh", "partial", "stale"]


class DatasetMeta(BaseModel):
    """Freshness and completeness shared by all player endpoints."""

    data_status: DataStatusOut
    refresh_error: str | None
    as_of: datetime
    last_successful_update: datetime


class RatingPoint(BaseModel):
    timestamp: datetime = Field(description="Game end time (UTC).")
    rating: int
    source: Literal["game_record"] = "game_record"
    game_id: int = Field(description="Internal id of the game the rating was reported with.")


class RatingHistoryResponse(DatasetMeta):
    username: str
    period: Period
    points: list[RatingPoint] = Field(description="Oldest first; no interpolated points.")
    rating_semantics: Literal["reported_with_game"] = Field(
        default="reported_with_game",
        description="The provider does not document whether a game rating is pre- or post-game.",
    )
    coverage: Literal["complete", "partial", "none"]
    games_considered: int
    games_without_rating: int
    duplicates_removed: int


class GroupStats(BaseModel):
    games_count: int = Field(description="Sample size.")
    wins: int
    losses: int
    draws: int
    unknown_results: int
    win_rate: float | None


class OpeningItem(GroupStats):
    opening_key: str | None = Field(description="Provider opening identifier; null = Unknown.")
    name: str
    eco_code: str | None
    is_unknown: bool


class OpeningsResponse(DatasetMeta):
    username: str
    period: Period
    sort: Literal["games", "win_rate", "name"]
    total_groups: int
    items: list[OpeningItem]


class OpponentItem(GroupStats):
    opponent_username: str = Field(description="Provider username (stable account identifier).")
    profile_url: str
    last_played_at: datetime
    last_rating: int | None = Field(
        description="Opponent rating reported with the most recent game; null if absent."
    )


class OpponentsResponse(DatasetMeta):
    username: str
    period: Period
    perspective: Literal["searched_player"] = Field(
        default="searched_player", description="Outcome counts are from the searched player's side."
    )
    sort: Literal["games", "win_rate", "name"]
    total_groups: int
    items: list[OpponentItem]
