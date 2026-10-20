"""Chess.com Published-Data API adapter.

Provider-specific HTTP and parsing stay inside this package (AGENT.md §5).
Verified contract and limitations: docs/specs/chess-com-provider.md.
"""

from app.providers.chess_com.client import ChessComHttpClient, ResourceKind, RetryPolicy
from app.providers.chess_com.provider import ChessComProvider, select_archive_months
from app.providers.chess_com.usernames import InvalidUsernameError, normalize_username

__all__ = [
    "ChessComHttpClient",
    "ChessComProvider",
    "InvalidUsernameError",
    "ResourceKind",
    "RetryPolicy",
    "normalize_username",
    "select_archive_months",
]
