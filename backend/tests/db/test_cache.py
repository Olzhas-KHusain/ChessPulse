"""Cache freshness, refresh, stale fallback and refresh coordination."""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.cache.policy import DatasetUnavailableError, DataStatus, Freshness, classify
from app.cache.service import REFRESH_IN_PROGRESS, PlayerDatasetCache, dataset_cache_key
from app.core.config import Settings
from app.models import CacheMetadata, CacheStatus, Game
from app.providers.errors import ProviderError, ProviderErrorCode
from app.providers.types import ArchiveMonth
from tests.ingestion_helpers import NOW, OWNER, FakeProvider, game

pytestmark = pytest.mark.integration

OCT = ArchiveMonth(2026, 10)
TTL = timedelta(hours=12)
COOLDOWN = timedelta(minutes=5)
KEY = dataset_cache_key(OWNER)


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://u:p@localhost:5432/db",
        cache_ttl_seconds=int(TTL.total_seconds()),
        refresh_failure_cooldown_seconds=int(COOLDOWN.total_seconds()),
    )


def _provider(games: int = 2) -> FakeProvider:
    return FakeProvider(
        months={OCT: [game(NOW - timedelta(days=1, hours=i)) for i in range(games)]}
    )


def _ensure(session: Session, provider: FakeProvider, at=NOW):  # type: ignore[no-untyped-def]
    return PlayerDatasetCache(session, provider, _settings()).ensure_dataset(OWNER, at)


def _state(session: Session) -> CacheMetadata:
    session.expire_all()
    return session.scalars(select(CacheMetadata).where(CacheMetadata.cache_key == KEY)).one()


def _game_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Game)) or 0


OUTAGE = ProviderError(ProviderErrorCode.UPSTREAM_UNAVAILABLE, "down")


def test_cache_miss_refreshes_and_records_freshness(session: Session) -> None:
    provider = _provider()
    status = _ensure(session, provider)

    assert status.data_status is DataStatus.FRESH
    assert status.refreshed
    assert status.last_successful_update == NOW
    assert status.expires_at == NOW + TTL
    assert status.eligible_games == 2
    assert "profile" in provider.calls
    state = _state(session)
    assert (state.status, state.record_count, state.is_complete) == (CacheStatus.SUCCEEDED, 2, True)


def test_fresh_cache_is_served_without_upstream_requests(session: Session) -> None:
    _ensure(session, _provider())
    second = _provider()
    status = _ensure(session, second, NOW + TTL - timedelta(seconds=1))
    assert second.calls == []
    assert not status.refreshed
    assert status.data_status is DataStatus.FRESH
    assert status.last_successful_update == NOW


def test_expired_cache_refreshes_successfully(session: Session) -> None:
    _ensure(session, _provider(games=1))
    later = NOW + TTL
    provider = _provider(games=2)
    status = _ensure(session, provider, later)
    assert provider.calls and status.refreshed
    assert status.last_successful_update == later
    assert status.expires_at == later + TTL


def test_expired_cache_with_failed_refresh_serves_stale_data(session: Session) -> None:
    _ensure(session, _provider(games=2))
    later = NOW + TTL + timedelta(hours=1)
    status = _ensure(session, FakeProvider(profile_error=OUTAGE), later)

    assert status.data_status is DataStatus.STALE
    assert status.refresh_error == "UPSTREAM_UNAVAILABLE"
    assert status.last_successful_update == NOW  # not the failed attempt
    assert status.eligible_games == 2
    assert _game_count(session) == 2  # good data was not replaced
    state = _state(session)
    assert state.status is CacheStatus.FAILED
    assert state.last_success_at == NOW
    assert state.next_refresh_not_before == later + COOLDOWN


def test_failed_refresh_without_cache_is_unavailable(session: Session) -> None:
    with pytest.raises(DatasetUnavailableError) as excinfo:
        _ensure(session, FakeProvider(profile_error=OUTAGE))
    assert excinfo.value.code == "UPSTREAM_UNAVAILABLE"
    assert excinfo.value.retry_after_seconds == COOLDOWN.total_seconds()


def test_confirmed_missing_player_is_not_masked(session: Session) -> None:
    missing = ProviderError(ProviderErrorCode.PLAYER_NOT_FOUND, "missing")
    with pytest.raises(ProviderError) as excinfo:
        _ensure(session, FakeProvider(profile_error=missing))
    assert excinfo.value.is_confirmed_missing_player


def test_rate_limit_retry_after_is_respected(session: Session) -> None:
    _ensure(session, _provider())
    expired = NOW + TTL
    limited = ProviderError(ProviderErrorCode.UPSTREAM_RATE_LIMITED, "429", retry_after=900)
    first = _ensure(session, FakeProvider(profile_error=limited), expired)
    assert first.data_status is DataStatus.STALE
    assert first.retry_after_seconds == 900  # Retry-After longer than the cooldown wins

    during = _provider()
    second = _ensure(session, during, expired + timedelta(minutes=10))
    assert during.calls == []  # no request while the provider asked us to wait
    assert second.data_status is DataStatus.STALE
    assert second.refresh_error == "UPSTREAM_RATE_LIMITED"

    after = _provider()
    third = _ensure(session, after, expired + timedelta(minutes=16))
    assert after.calls and third.data_status is DataStatus.FRESH


def test_failure_cooldown_also_applies_without_cache(session: Session) -> None:
    with pytest.raises(DatasetUnavailableError):
        _ensure(session, FakeProvider(profile_error=OUTAGE))
    retry = _provider()
    with pytest.raises(DatasetUnavailableError) as excinfo:
        _ensure(session, retry, NOW + timedelta(minutes=1))
    assert retry.calls == []
    assert excinfo.value.retry_after_seconds == pytest.approx(240)


def test_empty_valid_dataset_is_fresh_with_zero_games(session: Session) -> None:
    status = _ensure(session, FakeProvider(months={}))
    assert status.data_status is DataStatus.FRESH
    assert status.eligible_games == 0
    assert status.refresh_error is None


def test_incomplete_refresh_is_partial(session: Session) -> None:
    provider = FakeProvider(
        months={ArchiveMonth(2026, 9): OUTAGE, OCT: [game(NOW - timedelta(days=1))]}
    )
    status = _ensure(session, provider)
    assert status.data_status is DataStatus.PARTIAL
    assert status.refresh_error == "INGESTION_INCOMPLETE"
    # Served again from cache, still flagged as partial.
    assert _ensure(session, _provider(), NOW + timedelta(hours=1)).data_status is DataStatus.PARTIAL


def _hold_lock(engine: Engine, key: str) -> tuple[threading.Event, threading.Event]:
    held, release = threading.Event(), threading.Event()

    def worker() -> None:
        with engine.connect() as conn:
            conn.scalar(select(func.pg_advisory_lock(func.hashtextextended(key, 0))))
            held.set()
            release.wait(10)
            conn.scalar(select(func.pg_advisory_unlock(func.hashtextextended(key, 0))))

    threading.Thread(target=worker, daemon=True).start()
    assert held.wait(5)
    return held, release


def test_concurrent_refresh_serves_stale_instead_of_duplicating(
    session: Session, migrated_engine: Engine
) -> None:
    _ensure(session, _provider())
    _, release = _hold_lock(migrated_engine, KEY)
    try:
        provider = _provider()
        status = _ensure(session, provider, NOW + TTL)
    finally:
        release.set()
    assert provider.calls == []
    assert status.data_status is DataStatus.STALE
    assert status.refresh_error == REFRESH_IN_PROGRESS


def test_concurrent_refresh_without_cache_is_unavailable(
    session: Session, migrated_engine: Engine
) -> None:
    _, release = _hold_lock(migrated_engine, KEY)
    try:
        provider = _provider()
        with pytest.raises(DatasetUnavailableError) as excinfo:
            _ensure(session, provider)
    finally:
        release.set()
    assert excinfo.value.code == REFRESH_IN_PROGRESS
    assert provider.calls == []


def test_classify_states() -> None:
    assert classify(None, NOW) is Freshness.MISSING
    row = CacheMetadata(last_success_at=NOW, expires_at=NOW + TTL)
    assert classify(row, NOW) is Freshness.FRESH
    assert classify(row, NOW + TTL) is Freshness.EXPIRED  # expiry is exclusive
    row.next_refresh_not_before = NOW + TTL + COOLDOWN
    assert classify(row, NOW + TTL) is Freshness.COOLDOWN
