"""Canonical game records and player-perspective associations."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UtcDateTime, str_enum
from app.models.enums import GameResult, PlayerColor, PlayerResult, Provider, TimeClass
from app.models.mixins import IdPrimaryKeyMixin, TimestampMixin
from app.models.opening import Opening
from app.models.player import Player


class Game(IdPrimaryKeyMixin, TimestampMixin, Base):
    """One provider game, stored once regardless of how many archives contain it.

    * ``(provider, provider_game_id)`` is the deduplication key. ``provider_game_id``
      is an opaque, provider-derived identifier and is NOT NULL: a game without a
      stable identifier is not persisted (see docs/specs/database-schema.md).
    * ``played_at`` is the authoritative timestamp used by the analysis window. For
      Chess.com it is the game's ``end_time``, the moment the game was completed.
    * ``white_rating`` / ``black_rating`` are the ratings exactly as reported in the
      game record; nothing is derived or interpolated.
    * Relationships use ``lazy="raise"`` so accidental per-row lazy loading (N+1)
      fails loudly; queries must load what they need explicitly.
    """

    __tablename__ = "games"
    __table_args__ = (
        UniqueConstraint("provider", "provider_game_id"),
        CheckConstraint("char_length(provider_game_id) > 0", name="provider_game_id_not_empty"),
        CheckConstraint("white_player_id <> black_player_id", name="distinct_participants"),
        CheckConstraint(
            "white_rating IS NULL OR white_rating >= 0", name="white_rating_non_negative"
        ),
        CheckConstraint(
            "black_rating IS NULL OR black_rating >= 0", name="black_rating_non_negative"
        ),
        Index(None, "played_at"),
        Index(None, "time_class", "played_at"),
        Index(None, "white_player_id"),
        Index(None, "black_player_id"),
        Index(None, "opening_id"),
    )

    provider: Mapped[Provider] = mapped_column(str_enum(Provider, "provider"), nullable=False)
    provider_game_id: Mapped[str] = mapped_column(String(128), nullable=False)
    game_url: Mapped[str | None] = mapped_column(Text)
    played_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    time_class: Mapped[TimeClass] = mapped_column(
        str_enum(TimeClass, "time_class", length=16), nullable=False
    )
    # Raw provider time control, e.g. "600+5". Displayed as-is; never parsed into a class.
    time_control: Mapped[str | None] = mapped_column(String(32))
    rated: Mapped[bool | None] = mapped_column(Boolean)
    white_player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="RESTRICT"), nullable=False
    )
    black_player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="RESTRICT"), nullable=False
    )
    white_rating: Mapped[int | None] = mapped_column(Integer)
    black_rating: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[GameResult] = mapped_column(
        str_enum(GameResult, "game_result", length=16), nullable=False
    )
    opening_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("openings.id", ondelete="SET NULL")
    )
    # Raw PGN as returned by the provider, when available. Whether it is stored
    # permanently is an open decision (spec §20); the column is nullable either way.
    pgn: Mapped[str | None] = mapped_column(Text)

    white_player: Mapped[Player] = relationship(foreign_keys=[white_player_id], lazy="raise")
    black_player: Mapped[Player] = relationship(foreign_keys=[black_player_id], lazy="raise")
    opening: Mapped[Opening | None] = relationship(lazy="raise")

    def __repr__(self) -> str:
        return (
            f"Game(id={self.id!r}, provider={self.provider!r}, "
            f"provider_game_id={self.provider_game_id!r})"
        )


class PlayerGame(IdPrimaryKeyMixin, TimestampMixin, Base):
    """A game as seen by a tracked (searched) player.

    A row means "this game belongs to this player's ingested dataset". Rows are
    created for searched players only, not for every opponent, so the presence of
    rows never suggests that an opponent's own archive has been fetched.

    ``color`` and ``result`` are denormalized from ``games`` to keep analytics
    queries simple. Their consistency with the game's participants and result is
    enforced by deferred constraint triggers defined in the initial migration
    (``ck_player_games_participant`` and ``ck_player_games_result_matches_game``).
    """

    __tablename__ = "player_games"
    __table_args__ = (
        UniqueConstraint("player_id", "game_id"),
        # At most one tracked perspective per side of a game.
        UniqueConstraint("game_id", "color"),
    )

    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    game_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("games.id", ondelete="CASCADE"), nullable=False
    )
    color: Mapped[PlayerColor] = mapped_column(
        str_enum(PlayerColor, "player_color", length=8), nullable=False
    )
    result: Mapped[PlayerResult] = mapped_column(
        str_enum(PlayerResult, "player_result", length=8), nullable=False
    )

    player: Mapped[Player] = relationship(lazy="raise")
    game: Mapped[Game] = relationship(lazy="raise")

    def __repr__(self) -> str:
        return (
            f"PlayerGame(player_id={self.player_id!r}, game_id={self.game_id!r}, "
            f"color={self.color!r}, result={self.result!r})"
        )
