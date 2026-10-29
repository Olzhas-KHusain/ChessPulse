"""Enumerations persisted in the database.

Each enum is stored as VARCHAR with a CHECK constraint (see ``app.db.types.str_enum``).
Adding a member requires a migration that rewrites the corresponding CHECK constraint.
"""

from __future__ import annotations

from enum import StrEnum


class Provider(StrEnum):
    """External data provider a record came from."""

    CHESS_COM = "chess_com"


class TimeClass(StrEnum):
    """Provider-documented speed category of a game (Chess.com ``time_class``).

    Only ``rapid`` games are eligible for analytics. Other classes are allowed by the
    schema so that a misclassified record is rejected by policy, not by a crash, but
    ingestion is expected to persist Rapid games only.
    """

    RAPID = "rapid"
    BLITZ = "blitz"
    BULLET = "bullet"
    DAILY = "daily"


class GameResult(StrEnum):
    """Outcome of a game as a whole (not from any player's perspective)."""

    WHITE_WIN = "white_win"
    BLACK_WIN = "black_win"
    DRAW = "draw"
    # The provider data did not allow a confident classification. Never counted as a loss.
    UNKNOWN = "unknown"


class PlayerColor(StrEnum):
    """Side a player had in a game."""

    WHITE = "white"
    BLACK = "black"


class PlayerResult(StrEnum):
    """Outcome from one player's perspective (spec §6.3)."""

    WIN = "win"
    LOSS = "loss"
    DRAW = "draw"
    UNKNOWN = "unknown"


class OpeningSource(StrEnum):
    """Origin of an opening identifier."""

    CHESS_COM = "chess_com"


class CacheResourceType(StrEnum):
    """Provider resources whose freshness is tracked in ``cache_metadata``.

    Values mirror documented Chess.com PubAPI resources: the player profile, the
    player stats (current ratings), the list of monthly archives, and one monthly
    game archive.
    """

    PLAYER_PROFILE = "player_profile"
    PLAYER_STATS = "player_stats"
    GAME_ARCHIVES = "game_archives"
    GAME_ARCHIVE_MONTH = "game_archive_month"
    # The whole normalized dataset of one player (profile, rating, window archives);
    # this is the unit whose freshness the cache policy decides.
    PLAYER_DATASET = "player_dataset"


class AnalysisJobStatus(StrEnum):
    """Lifecycle of one engine-analysis job.

    ``queued`` jobs are claimed by a worker with ``FOR UPDATE SKIP LOCKED``; the
    worker moves the row to ``running``, then to ``completed`` or ``failed``.
    """

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CacheStatus(StrEnum):
    """Outcome of the most recent refresh attempt for a cached resource.

    Freshness (fresh/stale) is intentionally NOT stored: it changes with the clock,
    so it is derived at read time from ``expires_at`` and ``last_success_at``.
    """

    REFRESHING = "refreshing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def player_result_for(color: PlayerColor, result: GameResult) -> PlayerResult:
    """Translate a game result into the perspective of the player with ``color``.

    This is the single source of truth for the rule; the database enforces the same
    mapping with a constraint trigger on ``player_games``.
    """
    if result is GameResult.DRAW:
        return PlayerResult.DRAW
    if result is GameResult.UNKNOWN:
        return PlayerResult.UNKNOWN
    winner = PlayerColor.WHITE if result is GameResult.WHITE_WIN else PlayerColor.BLACK
    return PlayerResult.WIN if color is winner else PlayerResult.LOSS
