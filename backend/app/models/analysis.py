"""Engine analysis results and the durable job queue that produces them.

Engine analysis is deliberately decoupled from request handling: a request only
enqueues a job, and a separate worker process runs Stockfish. The queue lives in
PostgreSQL, so no extra infrastructure (Redis, Celery) is required.

Cache key: ``(game_id, profile_hash)``. ``profile_hash`` is a SHA-256 of the
analysis configuration, so changing the depth or engine options produces new
results instead of silently reusing incomparable ones.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UtcDateTime, str_enum
from app.models.enums import AnalysisJobStatus
from app.models.mixins import IdPrimaryKeyMixin, TimestampMixin


class AnalysisJob(IdPrimaryKeyMixin, TimestampMixin, Base):
    """One pending or finished request to analyse one game.

    ``attempts`` counts claims, not failures: it is incremented when a worker
    picks the job up. A job that fails is retried until ``attempts`` reaches the
    configured limit, after which it stays ``failed`` with a short error code.

    Invariants:

    * ``profile_hash`` is a lowercase SHA-256 hex digest;
    * a ``failed`` job always names an ``error_code``;
    * ``finished_at`` exists only for terminal states.
    """

    __tablename__ = "analysis_jobs"
    __table_args__ = (
        UniqueConstraint("game_id", "profile_hash", name="uq_analysis_jobs_game_profile"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        CheckConstraint("profile_hash ~ '^[a-f0-9]{64}$'", name="profile_hash_hex"),
        CheckConstraint(
            "status <> 'failed' OR error_code IS NOT NULL",
            name="failed_requires_error",
        ),
        CheckConstraint(
            "finished_at IS NULL OR status IN ('completed', 'failed')",
            name="finished_only_when_terminal",
        ),
        Index(None, "status", "created_at"),
    )

    game_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("games.id", ondelete="CASCADE"), nullable=False
    )
    profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[AnalysisJobStatus] = mapped_column(
        str_enum(AnalysisJobStatus, "analysis_job_status", length=16),
        nullable=False,
        server_default=text("'queued'"),
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # Short machine code (e.g. ``ENGINE_TIMEOUT``); never a raw exception message.
    error_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    def __repr__(self) -> str:
        return f"AnalysisJob(id={self.id!r}, game_id={self.game_id!r}, status={self.status!r})"


class GameAnalysis(IdPrimaryKeyMixin, TimestampMixin, Base):
    """A completed engine analysis of one game under one configuration profile.

    The payload is stored as JSONB because it is read as a whole document and its
    per-ply shape is defined by the analysis schema version, not by the relational
    model. Aggregate queries over many games will later be served by a separate
    summary table rather than by scanning JSONB.
    """

    __tablename__ = "game_analysis"
    __table_args__ = (
        UniqueConstraint("game_id", "profile_hash", name="uq_game_analysis_game_profile"),
        CheckConstraint("depth > 0", name="depth_positive"),
        CheckConstraint("analysis_ms >= 0", name="analysis_ms_non_negative"),
        CheckConstraint("profile_hash ~ '^[a-f0-9]{64}$'", name="profile_hash_hex"),
        Index(None, "profile_hash"),
    )

    game_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("games.id", ondelete="CASCADE"), nullable=False
    )
    profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_name: Mapped[str] = mapped_column(String(32), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    analysis_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    def __repr__(self) -> str:
        return (
            f"GameAnalysis(game_id={self.game_id!r}, "
            f"engine={self.engine_name!r} {self.engine_version!r})"
        )
