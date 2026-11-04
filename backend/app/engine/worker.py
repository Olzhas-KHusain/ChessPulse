"""Durable analysis worker: claim a job, run Stockfish, store the result.

Concurrency model: any number of worker processes may run. ``claim_job`` uses
``FOR UPDATE SKIP LOCKED``, so two workers never take the same row and a slow
engine search never blocks another worker.

Failure model:

* a game that cannot be analysed (missing or malformed PGN) fails immediately;
* an engine failure is retried up to ``analysis_job_max_attempts`` claims;
* a job left ``running`` by a dead worker is returned to the queue on startup.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.engine.game import AnalysisError, Engine, analyse_game
from app.engine.uci import EngineError
from app.models import AnalysisJob, AnalysisJobStatus, Game, GameAnalysis

logger = logging.getLogger(__name__)

type EngineFactory = Callable[[], AbstractContextManager[Engine]]


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    id: int
    game_id: int
    profile_hash: str
    attempts: int


_CLAIM_SQL = text(
    """
    UPDATE analysis_jobs
       SET status = 'running',
           attempts = attempts + 1,
           started_at = now(),
           updated_at = now()
     WHERE id = (
           SELECT id
             FROM analysis_jobs
            WHERE status = 'queued'
            ORDER BY created_at, id
            FOR UPDATE SKIP LOCKED
            LIMIT 1
     )
    RETURNING id, game_id, profile_hash, attempts
    """
)

_STALE_SQL = text(
    """
    UPDATE analysis_jobs
       SET status = 'queued',
           started_at = NULL,
           error_code = 'WORKER_LOST',
           updated_at = now()
     WHERE status = 'running'
       AND started_at < now() - make_interval(mins => :minutes)
    RETURNING id
    """
)


def claim_job(session: Session) -> ClaimedJob | None:
    """Atomically move one queued job to ``running`` and return it."""
    row = session.execute(_CLAIM_SQL).mappings().first()
    if row is None:
        return None
    return ClaimedJob(
        id=row["id"],
        game_id=row["game_id"],
        profile_hash=row["profile_hash"],
        attempts=row["attempts"],
    )


def requeue_stale_jobs(session: Session, older_than_minutes: int) -> int:
    """Return jobs abandoned by a dead worker to the queue."""
    result = session.execute(_STALE_SQL, {"minutes": older_than_minutes})
    session.commit()
    return len(result.all())


def _now() -> datetime:
    return datetime.now(UTC)


def _fail(session: Session, job: ClaimedJob, code: str) -> None:
    row = session.get_one(AnalysisJob, job.id)
    row.status = AnalysisJobStatus.FAILED
    row.error_code = code
    row.finished_at = _now()
    session.commit()


def _retry_or_fail(session: Session, job: ClaimedJob, code: str, max_attempts: int) -> str:
    if job.attempts >= max_attempts:
        _fail(session, job, code)
        return "failed"
    row = session.get_one(AnalysisJob, job.id)
    row.status = AnalysisJobStatus.QUEUED
    row.error_code = code
    row.started_at = None
    session.commit()
    return "retry"


def process_claimed(
    session: Session, job: ClaimedJob, engine_factory: EngineFactory, *, max_attempts: int
) -> str:
    """Analyse one claimed job. Returns ``completed``, ``failed`` or ``retry``."""
    game = session.get(Game, job.game_id)
    if game is None:  # the FK cascades, so this only happens on a concurrent delete
        _fail(session, job, "GAME_DELETED")
        return "failed"

    started = time.monotonic()
    try:
        with engine_factory() as engine:
            payload = analyse_game(game.pgn, engine)
    except AnalysisError as exc:
        logger.info("analysis rejected job=%s code=%s", job.id, exc.code)
        _fail(session, job, exc.code)
        return "failed"
    except EngineError as exc:
        logger.warning("engine failure job=%s code=%s", job.id, exc.code)
        return _retry_or_fail(session, job, exc.code, max_attempts=max_attempts)
    except Exception:
        logger.exception("unexpected analysis failure job=%s", job.id)
        return _retry_or_fail(session, job, "INTERNAL_ERROR", max_attempts=max_attempts)

    elapsed_ms = int((time.monotonic() - started) * 1000)
    engine_info = payload["engine"]
    session.execute(
        insert(GameAnalysis)
        .values(
            game_id=job.game_id,
            profile_hash=job.profile_hash,
            engine_name=engine_info["name"],
            engine_version=engine_info["version"],
            depth=engine_info["depth"],
            analysis_ms=elapsed_ms,
            payload=payload,
        )
        .on_conflict_do_nothing(constraint="uq_game_analysis_game_profile")
    )
    row = session.get_one(AnalysisJob, job.id)
    row.status = AnalysisJobStatus.COMPLETED
    row.error_code = None
    row.finished_at = _now()
    session.commit()
    logger.info("analysis completed job=%s game=%s ms=%s", job.id, job.game_id, elapsed_ms)
    return "completed"


def run_once(
    session_factory: sessionmaker[Session],
    engine_factory: EngineFactory,
    *,
    max_attempts: int,
) -> bool:
    """Process at most one job. Returns ``True`` when a job was claimed."""
    with session_factory() as session:
        job = claim_job(session)
        session.commit()
        if job is None:
            return False
        process_claimed(session, job, engine_factory, max_attempts=max_attempts)
        return True


def count_pending(session: Session) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(AnalysisJob)
            .where(AnalysisJob.status.in_([AnalysisJobStatus.QUEUED, AnalysisJobStatus.RUNNING]))
        )
        or 0
    )
