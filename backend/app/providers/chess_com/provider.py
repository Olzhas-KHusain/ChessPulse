"""Chess.com implementation of :class:`app.providers.base.GameDataProvider`."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from urllib.parse import quote

import httpx

from app.core.config import Settings
from app.providers.chess_com.client import ChessComHttpClient, ResourceKind, RetryPolicy
from app.providers.chess_com.normalize import (
    normalize_archive_index,
    normalize_month_archive,
    normalize_profile,
    normalize_stats,
)
from app.providers.chess_com.usernames import normalize_username
from app.providers.types import (
    ArchiveIndex,
    ArchiveMonth,
    MonthArchive,
    ProviderProfile,
    ProviderStats,
)

# Monthly archives are grouped by the month a game ended, but the documentation does
# not state the time zone. Months within this margin of the window are also fetched;
# exact window filtering happens later on ``played_at``.
ARCHIVE_MONTH_MARGIN = timedelta(days=1)


def select_archive_months(
    available: Iterable[ArchiveMonth], start: datetime, end: datetime
) -> list[ArchiveMonth]:
    """Months from ``available`` that can contain games ending in ``[start, end)``.

    Only months the provider listed are returned, so no request is made for an
    archive that does not exist.
    """
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")
    if start >= end:
        raise ValueError("start must be earlier than end")
    low, high = start - ARCHIVE_MONTH_MARGIN, end + ARCHIVE_MONTH_MARGIN
    return sorted(m for m in set(available) if m.start < high and m.end > low)


class ChessComProvider:
    """Read-only adapter over the documented PubAPI endpoints:

    * ``GET /pub/player/{username}`` — profile
    * ``GET /pub/player/{username}/stats`` — ratings (Rapid only is used)
    * ``GET /pub/player/{username}/games/archives`` — list of monthly archives
    * ``GET /pub/player/{username}/games/{YYYY}/{MM}`` — games of one month
    """

    def __init__(self, client: ChessComHttpClient) -> None:
        self._client = client

    @classmethod
    def from_settings(
        cls, settings: Settings, *, transport: httpx.BaseTransport | None = None
    ) -> ChessComProvider:
        retry = RetryPolicy(
            max_retries=settings.upstream_max_retries,
            max_delay_seconds=settings.upstream_max_retry_after_seconds,
        )
        client = ChessComHttpClient(
            user_agent=settings.chess_com_user_agent,
            timeout_seconds=settings.upstream_timeout_seconds,
            retry=retry,
            transport=transport,
        )
        return cls(client)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ChessComProvider:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _player_path(username: str) -> tuple[str, str]:
        normalized = normalize_username(username)
        return normalized, f"/player/{quote(normalized, safe='')}"

    def get_profile(self, username: str) -> ProviderProfile:
        """Resolve a public profile. A confirmed missing player raises
        ``ProviderError(PLAYER_NOT_FOUND)``; outages raise other codes."""
        _, path = self._player_path(username)
        response = self._client.get_json(path, ResourceKind.PROFILE)
        return normalize_profile(response.payload, response.meta)

    def get_stats(self, username: str) -> ProviderStats:
        _, path = self._player_path(username)
        response = self._client.get_json(f"{path}/stats", ResourceKind.STATS)
        return normalize_stats(response.payload, response.meta)

    def list_archive_months(self, username: str) -> ArchiveIndex:
        normalized, path = self._player_path(username)
        response = self._client.get_json(f"{path}/games/archives", ResourceKind.ARCHIVES)
        return normalize_archive_index(response.payload, normalized, response.meta)

    def get_month_archive(self, username: str, month: ArchiveMonth) -> MonthArchive:
        normalized, path = self._player_path(username)
        response = self._client.get_json(
            f"{path}/games/{month.year:04d}/{month.month:02d}", ResourceKind.MONTH_ARCHIVE
        )
        return normalize_month_archive(response.payload, normalized, month, response.meta)
