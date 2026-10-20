"""Serve a player's dataset from cache or refresh it under a controlled policy.

Rules (spec §12-13, AGENT.md §6):

* Fresh data is served without any upstream request.
* Expired or missing data is refreshed by at most one worker at a time per player
  (PostgreSQL advisory lock); other workers serve the last known good data marked
  ``stale`` instead of issuing duplicate requests.
* A failed refresh never deletes data: games stay in the domain tables, and the cache
  row keeps ``last_success_at`` / ``expires_at`` from the last good refresh.
* After a failure no new attempt is made before ``next_refresh_not_before``: the later
  of the provider's ``Retry-After`` and the configured failure cooldown.
* A confirmed missing player (``PLAYER_NOT_FOUND``) is re-raised, never masked by
  stale data.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.cache.policy import (
    DatasetStatus,
    DatasetUnavailableError,
    DataStatus,
    Freshness,
    classify,
)
from app.core.config import Settings
from app.models import CacheMetadata, CacheResourceType, CacheStatus, Provider
from app.providers.base import GameDataProvider
from app.providers.chess_com.usernames import normalize_username
from app.providers.errors import ProviderError, ProviderErrorCode
from app.repositories import CacheMetadataRepository, CacheState
from app.services.ingestion import GameIngestionService

logger = logging.getLogger(__name__)

REFRESH_IN_PROGRESS = "REFRESH_IN_PROGRESS"


def dataset_cache_key(username: str) -> str:
    return f"{Provider.CHESS_COM.value}:{CacheResourceType.PLAYER_DATASET.value}:{username}"


class PlayerDatasetCache:
    """Entry point used by API handlers before reading a player's analytics data."""

    def __init__(
        self,
        session: Session,
        provider: GameDataProvider,
        settings: Settings,
        *,
        ingestion_factory: Callable[[Session, GameDataProvider], GameIngestionService] = (
            GameIngestionService
        ),
    ) -> None:
        self._session = session
        self._provider = provider
        self._ttl = timedelta(seconds=settings.cache_ttl_seconds)
        self._cooldown = timedelta(seconds=settings.refresh_failure_cooldown_seconds)
        self._ingestion_factory = ingestion_factory
        self._cache = CacheMetadataRepository(session)

    def ensure_dataset(self, username: str, now: datetime) -> DatasetStatus:
        """Return freshness metadata, refreshing the dataset first when needed.

        Raises:
            InvalidUsernameError: malformed username (no request is made).
            ProviderError: the provider confirmed the player does not exist.
            DatasetUnavailableError: no usable data and the refresh failed or was skipped.
        """
        normalized = normalize_username(username)
        key = dataset_cache_key(normalized)
        state = self._cache.get_by_key(key)
        freshness = classify(state, now)

        if freshness is Freshness.FRESH:
            assert state is not None
            return self._served(state, now, refreshed=False)
        if freshness is Freshness.COOLDOWN:
            assert state is not None
            return self._serve_stale_or_raise(state, now, state.last_error_code)

        with self._refresh_lock(key) as acquired:
            if not acquired:
                self._log(normalized, "skipped_refresh_in_progress")
                return self._serve_stale_or_raise(state, now, REFRESH_IN_PROGRESS)
            # Another worker may have finished while we waited for the lock decision.
            self._session.expire_all()
            state = self._cache.get_by_key(key)
            if classify(state, now) is Freshness.FRESH:
                assert state is not None
                return self._served(state, now, refreshed=False)
            return self._refresh(normalized, key, state, now)

    # -- refresh --------------------------------------------------------------------

    def _refresh(
        self, username: str, key: str, previous: CacheMetadata | None, now: datetime
    ) -> DatasetStatus:
        base = self._state_from(key, previous, now)
        self._cache.save(replace(base, status=CacheStatus.REFRESHING))
        self._session.commit()
        try:
            report = self._ingestion_factory(self._session, self._provider).ingest_player(
                username, now
            )
        except ProviderError as error:
            retry_at = now + max(self._cooldown, timedelta(seconds=error.retry_after or 0))
            failed = self._cache.save(
                replace(
                    base,
                    status=CacheStatus.FAILED,
                    last_error_code=error.code.value,
                    last_error_at=now,
                    next_refresh_not_before=retry_at,
                )
            )
            self._session.commit()
            self._log(username, "refresh_failed", error_code=error.code.value)
            if error.code is ProviderErrorCode.PLAYER_NOT_FOUND:
                raise
            return self._serve_stale_or_raise(failed, now, error.code.value)

        stored = self._cache.save(
            replace(
                base,
                player_id=report.player_id,
                status=CacheStatus.SUCCEEDED,
                last_success_at=now,
                expires_at=now + self._ttl,
                record_count=report.eligible_games,
                is_complete=report.complete,
                last_error_code=None if report.complete else "INGESTION_INCOMPLETE",
                last_error_at=None if report.complete else now,
                next_refresh_not_before=None,
            )
        )
        self._session.commit()
        self._log(
            username,
            "refresh_succeeded",
            eligible_games=report.eligible_games,
            complete=report.complete,
        )
        return self._served(stored, now, refreshed=True)

    @staticmethod
    def _state_from(key: str, previous: CacheMetadata | None, now: datetime) -> CacheState:
        """New state that carries over everything known about the last good refresh."""
        if previous is None:
            return CacheState(
                cache_key=key,
                resource_type=CacheResourceType.PLAYER_DATASET,
                status=CacheStatus.REFRESHING,
                last_attempt_at=now,
            )
        return CacheState(
            cache_key=key,
            resource_type=CacheResourceType.PLAYER_DATASET,
            status=CacheStatus.REFRESHING,
            last_attempt_at=now,
            player_id=previous.player_id,
            last_success_at=previous.last_success_at,
            expires_at=previous.expires_at,
            record_count=previous.record_count,
            is_complete=previous.is_complete,
        )

    # -- serving --------------------------------------------------------------------

    def _served(self, state: CacheMetadata, now: datetime, *, refreshed: bool) -> DatasetStatus:
        assert state.last_success_at is not None and state.player_id is not None
        incomplete = state.is_complete is False
        return DatasetStatus(
            username=state.cache_key.rsplit(":", 1)[-1],
            player_id=state.player_id,
            data_status=DataStatus.PARTIAL if incomplete else DataStatus.FRESH,
            last_successful_update=state.last_success_at,
            expires_at=state.expires_at,
            eligible_games=state.record_count,
            refreshed=refreshed,
            refresh_error="INGESTION_INCOMPLETE" if incomplete else None,
        )

    def _serve_stale_or_raise(
        self, state: CacheMetadata | None, now: datetime, reason: str | None
    ) -> DatasetStatus:
        retry_after = None
        if state is not None and state.next_refresh_not_before is not None:
            retry_after = max(0.0, (state.next_refresh_not_before - now).total_seconds())
        code = reason or ProviderErrorCode.UPSTREAM_UNKNOWN_ERROR.value
        if state is None or state.last_success_at is None or state.player_id is None:
            raise DatasetUnavailableError(code, retry_after)
        return DatasetStatus(
            username=state.cache_key.rsplit(":", 1)[-1],
            player_id=state.player_id,
            data_status=DataStatus.STALE,
            last_successful_update=state.last_success_at,
            expires_at=state.expires_at,
            eligible_games=state.record_count,
            refreshed=False,
            refresh_error=code,
            retry_after_seconds=retry_after,
        )

    # -- coordination ---------------------------------------------------------------

    @contextmanager
    def _refresh_lock(self, key: str) -> Iterator[bool]:
        """Non-blocking per-player lock held on a dedicated connection.

        PostgreSQL session-level advisory locks work across processes and are released
        automatically if the process dies (the connection closes).
        """
        engine = self._session.get_bind()
        assert isinstance(engine, Engine)
        lock_id = func.hashtextextended(key, 0)
        with engine.connect() as conn:
            acquired = bool(conn.scalar(select(func.pg_try_advisory_lock(lock_id))))
            conn.commit()
            try:
                yield acquired
            finally:
                if acquired:
                    conn.execute(select(func.pg_advisory_unlock(lock_id)))
                    conn.commit()

    @staticmethod
    def _log(username: str, outcome: str, **fields: object) -> None:
        logger.info("dataset refresh", extra={"player": username, "outcome": outcome, **fields})
