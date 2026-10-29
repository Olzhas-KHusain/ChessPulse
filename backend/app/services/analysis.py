"""Engine-analysis requests: lookup, enqueueing and state reporting.

The API never runs Stockfish itself. A request either returns a cached analysis,
or records a durable job and returns its state; a worker process picks the job up.
This keeps request latency independent of engine speed and survives restarts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.analytics.window import analysis_window
from app.cache.service import PlayerDatasetCache
from app.core.config import Settings
from app.engine.profile import profile_hash
from app.models import AnalysisJob, AnalysisJobStatus, GameAnalysis, Player, Provider
from app.repositories import GameRepository
from app.schemas.analysis import AnalysisStateResponse
from app.services.games import GameNotFoundError


@dataclass(frozen=True, slots=True)
class AnalysisState:
    status: str
    error_code: str | None
    requested_at: datetime | None
    completed_at: datetime | None
    analysis: dict[str, Any] | None


def analysis_profile(settings: Settings) -> str:
    return profile_hash(
        depth=settings.analysis_depth,
        threads=settings.analysis_threads,
        hash_mb=settings.analysis_hash_mb,
    )


class AnalysisService:
    def __init__(self, session: Session, cache: PlayerDatasetCache, settings: Settings) -> None:
        self._session = session
        self._cache = cache
        self._settings = settings
        self._games = GameRepository(session)

    def _game(self, username: str, game_id: str, now: datetime) -> tuple[Player, int]:
        if not 1 <= len(game_id) <= 128:
            raise GameNotFoundError(game_id)
        status = self._cache.ensure_dataset(username, now)
        window = analysis_window(now)
        row = self._games.get_player_game(
            status.player_id, Provider.CHESS_COM, game_id, start=window.start, end=window.end
        )
        if row is None:
            raise GameNotFoundError(game_id)
        player = self._session.get_one(Player, status.player_id)
        return player, row.game.id

    def _read_state(self, game_db_id: int) -> AnalysisState:
        profile = analysis_profile(self._settings)
        analysis = self._session.scalar(
            select(GameAnalysis).where(
                GameAnalysis.game_id == game_db_id,
                GameAnalysis.profile_hash == profile,
            )
        )
        job = self._session.scalar(
            select(AnalysisJob).where(
                AnalysisJob.game_id == game_db_id,
                AnalysisJob.profile_hash == profile,
            )
        )
        if analysis is not None:
            return AnalysisState(
                status="completed",
                error_code=None,
                requested_at=job.created_at if job else analysis.created_at,
                completed_at=job.finished_at if job else analysis.created_at,
                analysis=analysis.payload,
            )
        if job is None:
            return AnalysisState("missing", None, None, None, None)
        return AnalysisState(
            status=job.status.value,
            error_code=job.error_code,
            requested_at=job.created_at,
            completed_at=job.finished_at,
            analysis=None,
        )

    def get_state(self, username: str, game_id: str, now: datetime) -> AnalysisStateResponse:
        player, game_db_id = self._game(username, game_id, now)
        state = self._read_state(game_db_id)
        return _response(player.username, game_id, state)

    def request(self, username: str, game_id: str, now: datetime) -> AnalysisStateResponse:
        """Return a cached analysis or enqueue a job; safe to call repeatedly."""
        player, game_db_id = self._game(username, game_id, now)
        state = self._read_state(game_db_id)
        if state.status == "completed":
            return _response(player.username, game_id, state)

        profile = analysis_profile(self._settings)
        stmt = insert(AnalysisJob).values(
            game_id=game_db_id,
            profile_hash=profile,
            status=AnalysisJobStatus.QUEUED,
        )
        # Re-requesting a failed job resets it; an active job keeps its progress.
        stmt = stmt.on_conflict_do_update(
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
        self._session.execute(stmt)
        self._session.commit()
        return _response(
            player.username,
            game_id,
            self._read_state(game_db_id),
        )


def _response(username: str, game_id: str, state: AnalysisState) -> AnalysisStateResponse:
    return AnalysisStateResponse(
        username=username,
        game_id=game_id,
        status=state.status,
        error_code=state.error_code,
        requested_at=state.requested_at,
        completed_at=state.completed_at,
        analysis=state.analysis,
    )
