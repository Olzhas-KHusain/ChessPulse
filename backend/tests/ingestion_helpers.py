"""In-memory provider and game builders for ingestion tests (synthetic data)."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.models import GameResult, PlayerResult, Provider, TimeClass
from app.providers.errors import ProviderError
from app.providers.types import (
    ArchiveIndex,
    ArchiveMonth,
    ExcludedGame,
    MonthArchive,
    ProviderGame,
    ProviderOpening,
    ProviderParticipant,
    ProviderProfile,
    ProviderStats,
    ResponseMeta,
)

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
META = ResponseMeta(fetched_at=NOW)
OWNER = "example_player"
_ids = itertools.count(1)

_OUTCOMES = {
    GameResult.WHITE_WIN: (PlayerResult.WIN, PlayerResult.LOSS),
    GameResult.BLACK_WIN: (PlayerResult.LOSS, PlayerResult.WIN),
    GameResult.DRAW: (PlayerResult.DRAW, PlayerResult.DRAW),
    GameResult.UNKNOWN: (PlayerResult.UNKNOWN, PlayerResult.UNKNOWN),
}


def game(
    played_at: datetime,
    *,
    owner_color: str = "white",
    opponent: str = "rival",
    result: GameResult = GameResult.WHITE_WIN,
    time_class: TimeClass = TimeClass.RAPID,
    rules: str | None = "chess",
    game_id: str | None = None,
    opening: ProviderOpening | None = None,
    white_rating: int | None = 1500,
    black_rating: int | None = 1490,
    pgn: str | None = None,
) -> ProviderGame:
    white_name, black_name = (OWNER, opponent) if owner_color == "white" else (opponent, OWNER)
    white_out, black_out = _OUTCOMES[result]
    gid = game_id or f"live:{next(_ids)}"
    return ProviderGame(
        provider=Provider.CHESS_COM,
        provider_game_id=gid,
        game_url=f"https://www.chess.com/game/live/{gid.split(':')[1]}",
        played_at=played_at,
        time_class=time_class,
        rules=rules,
        rated=True,
        time_control="600",
        white=ProviderParticipant(white_name, white_rating, None, white_out),
        black=ProviderParticipant(black_name, black_rating, None, black_out),
        result=result,
        opening=opening,
        pgn=pgn,
    )


@dataclass
class FakeProvider:
    """Implements ``GameDataProvider`` from in-memory data."""

    months: dict[ArchiveMonth, list[ProviderGame] | ProviderError] = field(default_factory=dict)
    excluded: dict[ArchiveMonth, list[ExcludedGame]] = field(default_factory=dict)
    profile_error: ProviderError | None = None
    stats_error: ProviderError | None = None
    username: str = OWNER
    player_id: str | None = "123"
    rapid_rating: int | None = 1523
    calls: list[str] = field(default_factory=list)

    def get_profile(self, username: str) -> ProviderProfile:
        self.calls.append("profile")
        if self.profile_error:
            raise self.profile_error
        return ProviderProfile(
            provider=Provider.CHESS_COM,
            username=self.username,
            provider_player_id=self.player_id,
            display_name=None,
            profile_url=None,
            avatar_url=None,
            account_status="basic",
            meta=META,
        )

    def get_stats(self, username: str) -> ProviderStats:
        self.calls.append("stats")
        if self.stats_error:
            raise self.stats_error
        if self.rapid_rating is None:
            return ProviderStats(False, None, None, META)
        return ProviderStats(True, self.rapid_rating, NOW, META)

    def list_archive_months(self, username: str) -> ArchiveIndex:
        self.calls.append("archives")
        return ArchiveIndex(months=tuple(sorted(self.months)), meta=META)

    def get_month_archive(self, username: str, month: ArchiveMonth) -> MonthArchive:
        self.calls.append(f"month:{month}")
        content = self.months[month]
        if isinstance(content, ProviderError):
            raise content
        return MonthArchive(
            username=username,
            month=month,
            games=tuple(content),
            excluded=tuple(self.excluded.get(month, [])),
            meta=META,
        )
