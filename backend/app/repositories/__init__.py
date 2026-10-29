"""Database access layer.

Repositories issue parameterized SQLAlchemy statements, batch multi-row writes,
and never commit: the service layer owns transaction boundaries.
"""

from app.repositories.analysis import AnalysedGameRow, AnalysisRepository
from app.repositories.cache_metadata import CacheMetadataRepository, CacheState
from app.repositories.games import (
    MAX_PAGE_SIZE,
    GameRecord,
    GameRepository,
    PageCursor,
    PlayerGameRow,
)
from app.repositories.openings import OpeningRecord, OpeningRepository
from app.repositories.players import PlayerProfile, PlayerRepository

__all__ = [
    "MAX_PAGE_SIZE",
    "AnalysedGameRow",
    "AnalysisRepository",
    "CacheMetadataRepository",
    "CacheState",
    "GameRecord",
    "GameRepository",
    "OpeningRecord",
    "OpeningRepository",
    "PageCursor",
    "PlayerGameRow",
    "PlayerProfile",
    "PlayerRepository",
]
