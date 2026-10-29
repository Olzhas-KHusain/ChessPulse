"""SQLAlchemy entities.

Every model must be imported here so it registers on ``Base.metadata``; Alembic
autogenerate and the schema-drift test compare the migrations against that metadata.
"""

from app.models.analysis import AnalysisJob, GameAnalysis
from app.models.cache_metadata import CacheMetadata
from app.models.enums import (
    AnalysisJobStatus,
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
    "AnalysisJob",
    "AnalysisJobStatus",
    "CacheMetadata",
    "CacheResourceType",
    "CacheStatus",
    "Game",
    "GameAnalysis",
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
