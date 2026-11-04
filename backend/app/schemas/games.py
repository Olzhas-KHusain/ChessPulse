"""Response schemas for the game list and game details endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.breakdowns import DatasetMeta
from app.schemas.overview import Period


class OpeningRef(BaseModel):
    opening_key: str
    name: str
    eco_code: str | None


class OpponentRef(BaseModel):
    username: str
    rating: int | None = Field(description="Rating reported with this game; null if absent.")


class GameSummary(BaseModel):
    game_id: str = Field(
        description="Stable provider game identifier, e.g. 'live:123'; use it for details."
    )
    played_at: datetime = Field(description="Game end time (UTC).")
    result: Literal["win", "loss", "draw", "unknown"] = Field(
        description="Outcome from the searched player's perspective."
    )
    color: Literal["white", "black"]
    player_rating: int | None = Field(
        description="Searched player's rating reported with the game."
    )
    opponent: OpponentRef
    time_control: str | None
    rated: bool | None
    opening: OpeningRef | None = Field(description="null = unknown opening.")
    game_url: str | None


class GameListResponse(DatasetMeta):
    username: str
    period: Period
    result_filter: Literal["win", "loss", "draw", "unknown"] | None
    items: list[GameSummary]
    next_cursor: str | None = Field(description="Pass as `cursor` for the next page; null = end.")


class PgnOut(BaseModel):
    status: Literal["available", "missing", "malformed"]
    headers: dict[str, str]
    moves_san: list[str] | None
    error: str | None
    raw: str | None = Field(description="Original PGN as provided by Chess.com, when stored.")


class GameDetailResponse(DatasetMeta):
    username: str
    game: GameSummary
    rating_semantics: Literal["reported_with_game"] = "reported_with_game"
    pgn: PgnOut
