"""Provider error categories (spec §8).

Provider adapters raise :class:`ProviderError` for every upstream failure. The
message is safe to log and to map into an API error: it never contains response
bodies, headers, or credentials.
"""

from __future__ import annotations

from enum import StrEnum


class ProviderErrorCode(StrEnum):
    """Machine-readable upstream failure categories."""

    # The provider confirmed (404/410 on the profile resource) that the player does not exist.
    PLAYER_NOT_FOUND = "PLAYER_NOT_FOUND"
    # A per-player sub-resource (stats, archive list, monthly archive) was not found.
    # Deliberately distinct from PLAYER_NOT_FOUND: it does not prove the player is missing.
    UPSTREAM_NOT_FOUND = "UPSTREAM_NOT_FOUND"
    UPSTREAM_RATE_LIMITED = "UPSTREAM_RATE_LIMITED"
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    UPSTREAM_INVALID_RESPONSE = "UPSTREAM_INVALID_RESPONSE"
    UPSTREAM_FORBIDDEN = "UPSTREAM_FORBIDDEN"
    UPSTREAM_UNKNOWN_ERROR = "UPSTREAM_UNKNOWN_ERROR"


class ProviderError(Exception):
    """An upstream request failed after the retry policy was exhausted or not applicable.

    Attributes:
        code: Failure category.
        status_code: Upstream HTTP status, when a response was received.
        retry_after: Seconds the provider asked us to wait (``Retry-After``), if any.
        attempts: Number of HTTP attempts made.
    """

    def __init__(
        self,
        code: ProviderErrorCode,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
        attempts: int = 1,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retry_after = retry_after
        self.attempts = attempts

    @property
    def is_confirmed_missing_player(self) -> bool:
        """True only when the provider confirmed the player does not exist."""
        return self.code is ProviderErrorCode.PLAYER_NOT_FOUND

    def __repr__(self) -> str:
        return (
            f"ProviderError(code={self.code.value!r}, status_code={self.status_code!r}, "
            f"retry_after={self.retry_after!r}, attempts={self.attempts!r})"
        )
