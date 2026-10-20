"""Overview service: cache policy + stored games + pure analytics."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.analytics.overview import GameOutcome, compute_overview
from app.analytics.window import analysis_window
from app.cache.policy import DataStatus
from app.cache.service import PlayerDatasetCache
from app.models import Player
from app.repositories import GameRepository
from app.schemas.overview import CurrentRating, OverviewResponse, Period, StreakOut


class OverviewService:
    def __init__(self, session: Session, cache: PlayerDatasetCache) -> None:
        self._session = session
        self._cache = cache
        self._games = GameRepository(session)

    def get_overview(self, username: str, now: datetime) -> OverviewResponse:
        status = self._cache.ensure_dataset(username, now)
        window = analysis_window(now)
        rows = self._games.list_outcomes(status.player_id, start=window.start, end=window.end)
        metrics = compute_overview(
            (GameOutcome(played_at, gid, result) for played_at, gid, result in rows),
            dataset_complete=status.data_status is not DataStatus.PARTIAL,
        )
        player = self._session.get_one(Player, status.player_id)

        rating = None
        if player.current_rapid_rating is not None:
            rating = CurrentRating(
                rating=player.current_rapid_rating, as_of=player.current_rapid_rating_at
            )
        missing: list[str] = []
        if rating is None:
            missing.append("current_rating")
        if status.data_status is DataStatus.PARTIAL:
            missing.append("games")

        streak = metrics.current_streak
        return OverviewResponse(
            username=player.username,
            period=Period(start=window.start, end=window.end),
            games_count=metrics.games_count,
            wins=metrics.wins,
            losses=metrics.losses,
            draws=metrics.draws,
            unknown_results=metrics.unknown_results,
            win_rate=metrics.win_rate,
            current_rating=rating.rating if rating else None,
            current_rating_detail=rating,
            current_streak=(
                StreakOut(type=streak.type.value, length=streak.length) if streak else None
            ),
            longest_winning_streak=metrics.longest_winning_streak,
            streak_may_be_incomplete=metrics.streak_may_be_incomplete,
            data_status=status.data_status.value,
            missing_sections=missing,
            refresh_error=status.refresh_error,
            as_of=now,
            last_successful_update=status.last_successful_update,
        )
