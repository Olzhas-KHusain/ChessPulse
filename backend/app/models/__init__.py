"""SQLAlchemy entities.

Every model must be imported here so it registers on ``Base.metadata``; Alembic
autogenerate and the schema-drift test compare the migrations against that metadata.
"""

from app.models.cache_metadata import CacheMetadata
from app.models.enums import (
    CacheResourceType,
    CacheStatus,
    GameResult,
    OpeningSource,
    PlayerColor,
    PlayerResult,
    Provider,
    TimeClass,
    player_result_for,
)
from app.models.game import Game, PlayerGame
from app.models.opening import Opening
from app.models.player import Player

__all__ = [
    "CacheMetadata",
    "CacheResourceType",
    "CacheStatus",
    "Game",
    "GameResult",
    "Opening",
    "OpeningSource",
    "Player",
    "PlayerColor",
    "PlayerGame",
    "PlayerResult",
    "Provider",
    "TimeClass",
    "player_result_for",
]
