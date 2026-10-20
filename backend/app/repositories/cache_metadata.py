"""Persistence for ``cache_metadata``.

Freshness policy (TTL, stale fallback, refresh coordination) belongs to the cache
layer and is implemented in a later issue; this repository only stores state.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import CacheMetadata, CacheResourceType, CacheStatus
from app.repositories._batching import require_lowercase


@dataclass(frozen=True, slots=True)
class CacheState:
    """Complete state of one cached resource, written as a unit."""

    cache_key: str
    resource_type: CacheResourceType
    status: CacheStatus
    last_attempt_at: datetime
    player_id: int | None = None
    last_success_at: datetime | None = None
    expires_at: datetime | None = None
    last_error_code: str | None = None
    last_error_at: datetime | None = None
    record_count: int | None = None
    next_refresh_not_before: datetime | None = None
    is_complete: bool | None = None


class CacheMetadataRepository:
    """Data access for cache metadata. Methods never commit."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_key(self, cache_key: str) -> CacheMetadata | None:
        require_lowercase(cache_key, "cache_key")
        return self._session.scalars(
            select(CacheMetadata).where(CacheMetadata.cache_key == cache_key)
        ).one_or_none()

    def save(self, state: CacheState) -> CacheMetadata:
        """Insert or replace the state stored under ``state.cache_key``.

        The caller supplies the complete state, including the last known
        ``last_success_at`` when recording a failure, so a failed refresh never
        erases the record of the last good fetch.
        """
        require_lowercase(state.cache_key, "cache_key")
        values = {f.name: getattr(state, f.name) for f in fields(state)}
        stmt = insert(CacheMetadata).values(values)
        upsert = stmt.on_conflict_do_update(
            index_elements=[CacheMetadata.cache_key],
            set_={
                **{name: stmt.excluded[name] for name in values if name != "cache_key"},
                "updated_at": func.now(),
            },
        ).returning(CacheMetadata)
        return self._session.scalars(upsert, execution_options={"populate_existing": True}).one()
