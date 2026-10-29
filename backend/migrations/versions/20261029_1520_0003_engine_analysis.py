"""Engine analysis: durable job queue and cached per-game results.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-29 15:20:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("profile_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="analysis_job_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        sa.CheckConstraint("profile_hash ~ '^[a-f0-9]{64}$'", name="profile_hash_hex"),
        sa.CheckConstraint(
            "status <> 'failed' OR error_code IS NOT NULL",
            name="failed_requires_error",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR status IN ('completed', 'failed')",
            name="finished_only_when_terminal",
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "profile_hash", name="uq_analysis_jobs_game_profile"),
    )
    op.create_index(
        "ix_analysis_jobs_status_created_at",
        "analysis_jobs",
        ["status", "created_at"],
    )

    op.create_table(
        "game_analysis",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("profile_hash", sa.String(length=64), nullable=False),
        sa.Column("engine_name", sa.String(length=32), nullable=False),
        sa.Column("engine_version", sa.String(length=32), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("analysis_ms", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("depth > 0", name="depth_positive"),
        sa.CheckConstraint("analysis_ms >= 0", name="analysis_ms_non_negative"),
        sa.CheckConstraint("profile_hash ~ '^[a-f0-9]{64}$'", name="profile_hash_hex"),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "profile_hash", name="uq_game_analysis_game_profile"),
    )
    op.create_index("ix_game_analysis_profile_hash", "game_analysis", ["profile_hash"])


def downgrade() -> None:
    op.drop_index("ix_game_analysis_profile_hash", table_name="game_analysis")
    op.drop_table("game_analysis")
    op.drop_index("ix_analysis_jobs_status_created_at", table_name="analysis_jobs")
    op.drop_table("analysis_jobs")
