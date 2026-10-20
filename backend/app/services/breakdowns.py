"""Rating history, opening and opponent statistics services."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.analytics.breakdowns import (
    GameRow,
    GroupSort,
    OpeningGroup,
    OpponentGroup,
    group_openings,
    group_opponents,
    rating_history,
    sort_groups,
)
from app.analytics.window import AnalysisWindow, analysis_window
from app.cache.policy import DatasetStatus, DataStatus
from app.cache.service import PlayerDatasetCache
from app.models import Player
from app.repositories import GameRepository
from app.schemas.breakdowns import (
    OpeningItem,
    OpeningsResponse,
    OpponentItem,
    OpponentsResponse,
    RatingHistoryResponse,
    RatingPoint,
)
from app.schemas.overview import Period

MAX_LIMIT = 100


class InvalidParameterError(ValueError):
    """A query parameter is syntactically valid but violates a documented rule."""

    def __init__(self, parameter: str, message: str) -> None:
        super().__init__(message)
        self.parameter = parameter
        self.message = message


class BreakdownService:
    def __init__(self, session: Session, cache: PlayerDatasetCache) -> None:
        self._session = session
        self._cache = cache
        self._games = GameRepository(session)

    def _load(
        self, username: str, now: datetime, window: AnalysisWindow
    ) -> tuple[DatasetStatus, Player, list[GameRow]]:
        status = self._cache.ensure_dataset(username, now)
        rows = self._games.list_breakdown_rows(status.player_id, start=window.start, end=window.end)
        return status, self._session.get_one(Player, status.player_id), rows

    @staticmethod
    def _meta(status: DatasetStatus, now: datetime) -> dict[str, object]:
        return {
            "data_status": status.data_status.value,
            "refresh_error": status.refresh_error,
            "as_of": now,
            "last_successful_update": status.last_successful_update,
        }

    def rating_history(
        self,
        username: str,
        now: datetime,
        from_: datetime | None = None,
        to: datetime | None = None,
    ) -> RatingHistoryResponse:
        window = _sub_window(analysis_window(now), from_, to)
        status, player, rows = self._load(username, now, window)
        history = rating_history(
            rows, dataset_complete=status.data_status is not DataStatus.PARTIAL
        )
        return RatingHistoryResponse(
            username=player.username,
            period=Period(start=window.start, end=window.end),
            points=[
                RatingPoint(timestamp=p.timestamp, rating=p.rating, game_id=p.game_id)
                for p in history.points
            ],
            coverage=history.coverage.value,
            games_considered=history.games_considered,
            games_without_rating=history.games_without_rating,
            duplicates_removed=history.duplicates_removed,
            **self._meta(status, now),
        )

    def openings(
        self, username: str, now: datetime, sort: GroupSort, limit: int
    ) -> OpeningsResponse:
        _check_limit(limit)
        window = analysis_window(now)
        status, player, rows = self._load(username, now, window)
        groups = sort_groups(group_openings(rows), sort, _opening_name)
        return OpeningsResponse(
            username=player.username,
            period=Period(start=window.start, end=window.end),
            sort=sort.value,
            total_groups=len(groups),
            items=[
                OpeningItem(
                    opening_key=g.key,
                    name=g.name,
                    eco_code=g.eco_code,
                    is_unknown=g.is_unknown,
                    **_stats(g),
                )
                for g in groups[:limit]
            ],
            **self._meta(status, now),
        )

    def opponents(
        self, username: str, now: datetime, sort: GroupSort, limit: int
    ) -> OpponentsResponse:
        _check_limit(limit)
        window = analysis_window(now)
        status, player, rows = self._load(username, now, window)
        groups = sort_groups(group_opponents(rows), sort, _opponent_name)
        items: list[OpponentItem] = []
        for g in groups[:limit]:
            assert g.last_played_at is not None
            items.append(
                OpponentItem(
                    opponent_username=g.username,
                    profile_url=f"https://www.chess.com/member/{g.username}",
                    last_played_at=g.last_played_at,
                    last_rating=g.last_rating,
                    **_stats(g),
                )
            )
        return OpponentsResponse(
            username=player.username,
            period=Period(start=window.start, end=window.end),
            sort=sort.value,
            total_groups=len(groups),
            items=items,
            **self._meta(status, now),
        )


def _opening_name(g: OpeningGroup) -> str:
    return g.name


def _opponent_name(g: OpponentGroup) -> str:
    return g.username


def _stats(g: OpeningGroup | OpponentGroup) -> dict[str, int | float | None]:
    c = g.counts
    return {
        "games_count": c.games_count,
        "wins": c.wins,
        "losses": c.losses,
        "draws": c.draws,
        "unknown_results": c.unknown_results,
        "win_rate": c.win_rate,
    }


def _check_limit(limit: int) -> None:
    if not 1 <= limit <= MAX_LIMIT:
        raise InvalidParameterError("limit", f"limit must be between 1 and {MAX_LIMIT}")


def _sub_window(
    window: AnalysisWindow, from_: datetime | None, to: datetime | None
) -> AnalysisWindow:
    """Optional ``from``/``to`` narrow the shared window; they can never widen it."""
    for name, value in (("from", from_), ("to", to)):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise InvalidParameterError(name, f"{name} must include a time zone (e.g. Z)")
    start = max(window.start, from_) if from_ else window.start
    end = min(window.end, to) if to else window.end
    if start >= end:
        raise InvalidParameterError(
            "from", "from must be earlier than to and inside the 30-day period"
        )
    return AnalysisWindow(start=start, end=end)
