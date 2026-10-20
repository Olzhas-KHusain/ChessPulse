"""Freshness and refresh-outcome tracking for provider resources."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UtcDateTime, str_enum
from app.models.enums import CacheResourceType, CacheStatus
from app.models.mixins import IdPrimaryKeyMixin, TimestampMixin


class CacheMetadata(IdPrimaryKeyMixin, TimestampMixin, Base):
    """Metadata about one cached provider resource.

    The cached data itself lives in the domain tables (players, games, ...); this
    table only records when a resource was attempted, when it last succeeded, when
    it expires and how the last attempt ended.

    Invariants enforced by CHECK constraints:

    * a ``succeeded`` status always has ``last_success_at``;
    * a ``failed`` status always has ``last_error_code`` and ``last_error_at``;
    * ``expires_at`` and ``record_count`` only exist after a successful fetch, so a
      failure can never look like a confirmed empty result;
    * ``last_error_code`` is a short machine code (e.g. ``UPSTREAM_TIMEOUT``), never
      a raw error payload.
    """

    __tablename__ = "cache_metadata"
    __table_args__ = (
        CheckConstraint("cache_key = lower(cache_key)", name="cache_key_lowercase"),
        CheckConstraint("char_length(cache_key) > 0", name="cache_key_not_empty"),
        CheckConstraint(
            "status <> 'succeeded' OR last_success_at IS NOT NULL",
            name="succeeded_requires_success_time",
        ),
        CheckConstraint(
            "status <> 'failed' OR (last_error_code IS NOT NULL AND last_error_at IS NOT NULL)",
            name="failed_requires_error",
        ),
        CheckConstraint(
            "expires_at IS NULL OR last_success_at IS NOT NULL",
            name="expiry_requires_success",
        ),
        CheckConstraint(
            "record_count IS NULL OR (record_count >= 0 AND last_success_at IS NOT NULL)",
            name="record_count_valid",
        ),
        CheckConstraint(
            "last_error_code IS NULL OR last_error_code ~ '^[A-Z][A-Z0-9_]*$'",
            name="error_code_format",
        ),
        Index(None, "expires_at"),
        Index(None, "player_id"),
    )

    player_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE")
    )
    resource_type: Mapped[CacheResourceType] = mapped_column(
        str_enum(CacheResourceType, "cache_resource_type"), nullable=False
    )
    # Normalized resource identifier, e.g. "chess_com:game_archive_month:example:2026-10".
    cache_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    status: Mapped[CacheStatus] = mapped_column(
        str_enum(CacheStatus, "cache_status", length=16), nullable=False
    )
    last_attempt_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_error_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    # Number of records in the last successful fetch; 0 means a confirmed empty result.
    record_count: Mapped[int | None] = mapped_column(Integer)
    # Earliest time another refresh may be attempted after a failure (provider
    # Retry-After or the configured failure cooldown). NULL = no restriction.
    next_refresh_not_before: Mapped[datetime | None] = mapped_column(UtcDateTime)
    # Whether the last successful refresh fetched every needed resource. NULL = unknown.
    is_complete: Mapped[bool | None] = mapped_column(Boolean)

    def __repr__(self) -> str:
        return f"CacheMetadata(cache_key={self.cache_key!r}, status={self.status!r})"
