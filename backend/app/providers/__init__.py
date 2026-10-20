"""External provider integrations.

Services depend on :class:`GameDataProvider` and the normalized types in
``app.providers.types``; only ``app.providers.chess_com`` knows Chess.com specifics.
"""

from app.providers.base import GameDataProvider
from app.providers.errors import ProviderError, ProviderErrorCode

__all__ = ["GameDataProvider", "ProviderError", "ProviderErrorCode"]
