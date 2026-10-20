"""Fetch, filter, and persist a player's eligible Rapid games.

Flow for one player (spec §12):

1. Resolve the profile (a confirmed missing player or an outage propagates as
   ``ProviderError`` and nothing is written).
2. Fetch the current Rapid rating; failure is tolerated and reported.
3. List monthly archives and fetch only months overlapping the analysis window.
   A failed month does not stop the others; it is recorded as incomplete.
4. Drop records the provider could not normalize and games that are not eligible
   (see ``eligibility.py``), counting every exclusion by reason.
5. Upsert participants, openings, games and the searched player's associations in
   one transaction. Upserts are idempotent, so repeated ingestion never inflates counts.
6. Record per-month fetch state in ``cache_metadata``; a failure keeps the last
   successful fetch time.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.analytics.window import AnalysisWindow, analysis_window
from app.models import CacheResourceType, CacheStatus, OpeningSource, PlayerColor, Provider
from app.providers.base import GameDataProvider
from app.providers.chess_com import select_archive_months
from app.providers.errors import ProviderError
from app.providers.types import ArchiveMonth, MonthArchive, ProviderGame, ProviderProfile
from app.repositories import (
    CacheMetadataRepository,
    CacheState,
    GameRecord,
    GameRepository,
    OpeningRecord,
    OpeningRepository,
    PlayerProfile,
    PlayerRepository,
)
from app.services.eligibility import ineligibility_reason

logger = logging.getLogger(__name__)

PROVIDER = Provider.CHESS_COM


def month_cache_key(username: str, month: ArchiveMonth) -> str:
    return f"{PROVIDER.value}:{CacheResourceType.GAME_ARCHIVE_MONTH.value}:{username}:{month}"


@dataclass(frozen=True, slots=True)
class IngestionReport:
    """What one ingestion run did. ``complete`` is False when data may be missing."""

    username: str
    player_id: int
    window: AnalysisWindow
    months_requested: tuple[ArchiveMonth, ...]
    # Months that could not be fetched, with the provider error code.
    months_failed: dict[str, str]
    eligible_games: int
    # Exclusion counts by reason (provider normalization and eligibility).
    excluded: dict[str, int]
    stats_error: str | None
    issues: tuple[str, ...] = field(default=())

    @property
    def complete(self) -> bool:
        return not self.months_failed


class GameIngestionService:
    """Ingests one player's games. The caller owns the session; this service commits
    once per successful run and rolls back on unexpected errors."""

    def __init__(self, session: Session, provider: GameDataProvider) -> None:
        self._session = session
        self._provider = provider
        self._players = PlayerRepository(session)
        self._games = GameRepository(session)
        self._openings = OpeningRepository(session)
        self._cache = CacheMetadataRepository(session)

    def ingest_player(self, username: str, now: datetime) -> IngestionReport:
        window = analysis_window(now)
        profile = self._provider.get_profile(username)
        try:
            report = self._ingest(profile, window, now)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        logger.info(
            "ingestion finished",
            extra={
                "player": report.username,
                "eligible_games": report.eligible_games,
                "excluded": report.excluded,
                "months_failed": report.months_failed,
            },
        )
        return report

    # -- steps ---------------------------------------------------------------------

    def _ingest(
        self, profile: ProviderProfile, window: AnalysisWindow, now: datetime
    ) -> IngestionReport:
        player_id = self._store_profile(profile)
        username = profile.username
        stats_error = self._store_stats(player_id, username)

        index = self._provider.list_archive_months(username)
        months = select_archive_months(index.months, window.start, window.end)

        excluded: Counter[str] = Counter()
        failed: dict[str, str] = {}
        eligible: dict[str, ProviderGame] = {}
        for month in months:
            try:
                archive = self._provider.get_month_archive(username, month)
            except ProviderError as error:
                failed[str(month)] = error.code.value
                self._record_month_failure(player_id, username, month, error, now)
                continue
            self._record_month_success(player_id, username, month, archive, now)
            excluded.update(item.reason.value for item in archive.excluded)
            for game in archive.games:
                reason = ineligibility_reason(game, window)
                if reason is not None:
                    excluded[reason.value] += 1
                elif game.provider_game_id in eligible:
                    excluded["duplicate_across_archives"] += 1
                else:
                    eligible[game.provider_game_id] = game

        self._persist(player_id, username, list(eligible.values()))
        return IngestionReport(
            username=username,
            player_id=player_id,
            window=window,
            months_requested=tuple(months),
            months_failed=failed,
            eligible_games=len(eligible),
            excluded=dict(excluded),
            stats_error=stats_error,
            issues=profile.issues + index.issues,
        )

    def _store_profile(self, profile: ProviderProfile) -> int:
        # A confirmed rename: same stable player_id, new username.
        if profile.provider_player_id is not None:
            existing = self._players.get_by_provider_player_id(PROVIDER, profile.provider_player_id)
            if existing is not None and existing.username != profile.username:
                self._players.rename(existing.id, profile.username)
        player = self._players.upsert_profile(
            PlayerProfile(
                provider=PROVIDER,
                username=profile.username,
                provider_player_id=profile.provider_player_id,
                display_name=profile.display_name,
                profile_url=profile.profile_url,
                avatar_url=profile.avatar_url,
            )
        )
        return player.id

    def _store_stats(self, player_id: int, username: str) -> str | None:
        try:
            stats = self._provider.get_stats(username)
        except ProviderError as error:
            return error.code.value  # keep the previously stored rating
        self._players.set_current_rapid_rating(player_id, stats.rapid_rating, stats.rapid_rating_at)
        return None

    def _persist(self, player_id: int, username: str, games: list[ProviderGame]) -> None:
        if not games:
            return
        usernames = {g.white.username for g in games} | {g.black.username for g in games}
        player_ids = self._players.ensure_usernames(PROVIDER, usernames)
        opening_ids = self._openings.ensure_openings(
            OpeningRecord(
                source=OpeningSource.CHESS_COM,
                source_opening_id=g.opening.source_opening_id,
                name=g.opening.name,
                eco_code=g.opening.eco_code,
            )
            for g in games
            if g.opening is not None
        )
        records = [
            GameRecord(
                provider=PROVIDER,
                provider_game_id=g.provider_game_id,
                played_at=g.played_at,
                time_class=g.time_class,
                result=g.result,
                white_player_id=player_ids[g.white.username],
                black_player_id=player_ids[g.black.username],
                game_url=g.game_url,
                time_control=g.time_control,
                rated=g.rated,
                white_rating=g.white.rating,
                black_rating=g.black.rating,
                opening_id=(
                    opening_ids[(OpeningSource.CHESS_COM, g.opening.source_opening_id)]
                    if g.opening is not None
                    else None
                ),
                pgn=g.pgn,
            )
            for g in games
        ]
        game_ids = self._games.upsert_games(records)
        self._games.link_player_games(
            player_id,
            [
                (
                    game_ids[(PROVIDER, g.provider_game_id)],
                    PlayerColor.WHITE if g.white.username == username else PlayerColor.BLACK,
                    g.result,
                )
                for g in games
            ],
        )

    def _record_month_success(
        self,
        player_id: int,
        username: str,
        month: ArchiveMonth,
        archive: MonthArchive,
        now: datetime,
    ) -> None:
        self._cache.save(
            CacheState(
                cache_key=month_cache_key(username, month),
                resource_type=CacheResourceType.GAME_ARCHIVE_MONTH,
                status=CacheStatus.SUCCEEDED,
                last_attempt_at=now,
                player_id=player_id,
                last_success_at=archive.meta.fetched_at,
                record_count=len(archive.games) + len(archive.excluded),
            )
        )

    def _record_month_failure(
        self,
        player_id: int,
        username: str,
        month: ArchiveMonth,
        error: ProviderError,
        now: datetime,
    ) -> None:
        key = month_cache_key(username, month)
        previous = self._cache.get_by_key(key)
        self._cache.save(
            CacheState(
                cache_key=key,
                resource_type=CacheResourceType.GAME_ARCHIVE_MONTH,
                status=CacheStatus.FAILED,
                last_attempt_at=now,
                player_id=player_id,
                # Never erase the record of the last good fetch.
                last_success_at=previous.last_success_at if previous else None,
                expires_at=previous.expires_at if previous else None,
                record_count=previous.record_count if previous else None,
                last_error_code=error.code.value,
                last_error_at=now,
            )
        )
