"""Provider interface used by services.

Services depend on this protocol, not on a concrete HTTP client, so tests can pass
an in-memory fake and the Chess.com adapter can be swapped or mocked.
"""

from __future__ import annotations

from typing import Protocol

from app.providers.types import (
    ArchiveIndex,
    ArchiveMonth,
    MonthArchive,
    ProviderProfile,
    ProviderStats,
)


class GameDataProvider(Protocol):
    """Read-only access to public player and game data.

    Every method accepts a raw username, normalizes and validates it (raising
    ``InvalidUsernameError``), and raises ``ProviderError`` for upstream failures.
    """

    def get_profile(self, username: str) -> ProviderProfile: ...

    def get_stats(self, username: str) -> ProviderStats: ...

    def list_archive_months(self, username: str) -> ArchiveIndex: ...

    def get_month_archive(self, username: str, month: ArchiveMonth) -> MonthArchive: ...
