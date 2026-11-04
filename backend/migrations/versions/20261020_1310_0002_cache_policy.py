"""Cache policy: player_dataset resource, refresh cooldown, completeness flag.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20 13:10:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECK = "ck_cache_metadata_cache_resource_type"
OLD_TYPES = "'player_profile', 'player_stats', 'game_archives', 'game_archive_month'"
NEW_TYPES = OLD_TYPES + ", 'player_dataset'"


def upgrade() -> None:
    op.add_column(
        "cache_metadata",
        sa.Column("next_refresh_not_before", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("cache_metadata", sa.Column("is_complete", sa.Boolean(), nullable=True))
    op.drop_constraint(op.f(CHECK), "cache_metadata", type_="check")
    op.create_check_constraint(op.f(CHECK), "cache_metadata", f"resource_type IN ({NEW_TYPES})")


def downgrade() -> None:
    op.execute("DELETE FROM cache_metadata WHERE resource_type = 'player_dataset'")
    op.drop_constraint(op.f(CHECK), "cache_metadata", type_="check")
    op.create_check_constraint(op.f(CHECK), "cache_metadata", f"resource_type IN ({OLD_TYPES})")
    op.drop_column("cache_metadata", "is_complete")
    op.drop_column("cache_metadata", "next_refresh_not_before")
