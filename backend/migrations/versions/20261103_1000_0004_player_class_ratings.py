"""Per-class current ratings on players (blitz, bullet, daily).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-03 10:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CLASSES = ("blitz", "bullet", "daily")


def upgrade() -> None:
    for name in _CLASSES:
        op.add_column("players", sa.Column(f"current_{name}_rating", sa.Integer(), nullable=True))
        op.add_column(
            "players",
            sa.Column(f"current_{name}_rating_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_check_constraint(
            f"current_{name}_rating_non_negative",
            "players",
            f"current_{name}_rating IS NULL OR current_{name}_rating >= 0",
        )
        op.create_check_constraint(
            f"current_{name}_rating_at_requires_rating",
            "players",
            f"current_{name}_rating_at IS NULL OR current_{name}_rating IS NOT NULL",
        )


def downgrade() -> None:
    for name in _CLASSES:
        op.drop_constraint(f"current_{name}_rating_at_requires_rating", "players", type_="check")
        op.drop_constraint(f"current_{name}_rating_non_negative", "players", type_="check")
        op.drop_column("players", f"current_{name}_rating_at")
        op.drop_column("players", f"current_{name}_rating")
