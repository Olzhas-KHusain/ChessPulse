"""Persistence for cross-game engine aggregates.

Only read queries over existing rows plus one idempotent job enqueue live here. The
aggregation itself is pure (``app.analytics.form``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, case, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from app.models import (
    AnalysisJob,
    AnalysisJobStatus,
    Game,
    GameAnalysis,
    Opening,
    Player,
    PlayerColor,
    PlayerGame,
    PlayerResult,
    TimeClass,
)


@dataclass(frozen=True, slots=True)
class AnalysedGameRow:
    """One completed analysis plus the metadata needed by the form report."""

    game_db_id: int
    provider_game_id: str
    played_at: datetime
    color: PlayerColor
    result: PlayerResult
    opponent: str
    opening_key: str | None
    opening_name: str | None
    game_url: str | None
    payload: dict[str, Any]


class AnalysisRepository:
    """Queries over ``game_analysis`` / ``analysis_jobs`` scoped to one player."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _scope(
        self,
        player_id: int,
        *,
        start: datetime,
        end: datetime,
        time_class: TimeClass,
    ) -> tuple[Any, ...]:
        return (
            PlayerGame.player_id == player_id,
            Game.time_class == time_class,
            Game.played_at >= start,
            Game.played_at < end,
        )

    def list_analysed_games(
        self,
        player_id: int,
        *,
        profile_hash: str,
        start: datetime,
        end: datetime,
        time_class: TimeClass = TimeClass.RAPID,
    ) -> list[AnalysedGameRow]:
        """Completed analyses of the player's games in the scope, oldest first."""
        white, black = aliased(Player), aliased(Player)
        is_white = PlayerGame.color == PlayerColor.WHITE
        opponent = case((is_white, black.username), else_=white.username)
        stmt = (
            select(
                Game.id,
                Game.provider_game_id,
                Game.played_at,
                PlayerGame.color,
                PlayerGame.result,
                opponent.label("opponent"),
                Opening.source_opening_id,
                Opening.name,
                Game.game_url,
                GameAnalysis.payload,
            )
            .join(PlayerGame, PlayerGame.game_id == Game.id)
            .join(white, white.id == Game.white_player_id)
            .join(black, black.id == Game.black_player_id)
            .outerjoin(Opening, Opening.id == Game.opening_id)
            .join(
                GameAnalysis,
                and_(
                    GameAnalysis.game_id == Game.id,
                    GameAnalysis.profile_hash == profile_hash,
                ),
            )
            .where(*self._scope(player_id, start=start, end=end, time_class=time_class))
            .order_by(Game.played_at, Game.id)
        )
        return [
            AnalysedGameRow(
                game_db_id=row.id,
                provider_game_id=row.provider_game_id,
                played_at=row.played_at,
                color=row.color,
                result=row.result,
                opponent=row.opponent,
                opening_key=row.source_opening_id,
                opening_name=row.name,
                game_url=row.game_url,
                payload=row.payload,
            )
            for row in self._session.execute(stmt)
        ]

    def list_scope_game_ids(
        self,
        player_id: int,
        *,
        start: datetime,
        end: datetime,
        time_class: TimeClass = TimeClass.RAPID,
    ) -> list[int]:
        stmt = (
            select(Game.id)
            .join(PlayerGame, PlayerGame.game_id == Game.id)
            .where(*self._scope(player_id, start=start, end=end, time_class=time_class))
            .order_by(Game.played_at, Game.id)
        )
        return list(self._session.scalars(stmt))

    def analysed_game_ids(self, game_ids: list[int], profile_hash: str) -> set[int]:
        if not game_ids:
            return set()
        return set(
            self._session.scalars(
                select(GameAnalysis.game_id).where(
                    GameAnalysis.game_id.in_(game_ids),
                    GameAnalysis.profile_hash == profile_hash,
                )
            )
        )

    def job_counts(
        self,
        player_id: int,
        *,
        profile_hash: str,
        start: datetime,
        end: datetime,
        time_class: TimeClass = TimeClass.RAPID,
    ) -> dict[str, int]:
        """Job counts by status for the player's games in the scope."""
        stmt = (
            select(AnalysisJob.status, func.count())
            .join(PlayerGame, PlayerGame.game_id == AnalysisJob.game_id)
            .join(Game, Game.id == AnalysisJob.game_id)
            .where(
                *self._scope(player_id, start=start, end=end, time_class=time_class),
                AnalysisJob.profile_hash == profile_hash,
            )
            .group_by(AnalysisJob.status)
        )
        return {status.value: count for status, count in self._session.execute(stmt)}

    def enqueue(self, game_ids: list[int], profile_hash: str) -> int:
        """Queue missing analyses; re-queue failed ones. Returns rows touched."""
        touched = 0
        for game_id in game_ids:
            stmt = (
                insert(AnalysisJob)
                .values(
                    game_id=game_id,
                    profile_hash=profile_hash,
                    status=AnalysisJobStatus.QUEUED,
                )
                .on_conflict_do_update(
                    constraint="uq_analysis_jobs_game_profile",
                    set_={
                        "status": AnalysisJobStatus.QUEUED,
                        "attempts": 0,
                        "error_code": None,
                        "started_at": None,
                        "finished_at": None,
                        "updated_at": text("now()"),
                    },
                    where=AnalysisJob.status == AnalysisJobStatus.FAILED,
                )
                .returning(AnalysisJob.id)
            )
            if self._session.execute(stmt).scalar_one_or_none() is not None:
                touched += 1
        return touched
