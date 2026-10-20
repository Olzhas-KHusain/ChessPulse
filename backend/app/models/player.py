"""Public player records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UtcDateTime, str_enum
from app.models.enums import Provider
from app.models.mixins import IdPrimaryKeyMixin, TimestampMixin

USERNAME_MAX_LENGTH = 64


class Player(IdPrimaryKeyMixin, TimestampMixin, Base):
    """A provider account: either a searched player or an opponent seen in a game.

    Identity rules (see docs/specs/database-schema.md):

    * ``(provider, username)`` is unique; usernames are stored lowercase because
      Chess.com usernames are case-insensitive.
    * ``provider_player_id`` holds Chess.com's profile ``player_id`` when the profile
      has been fetched. It is unique when present and NULL for opponents known only
      from game records, which do not carry that identifier.
    """

    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("provider", "username"),
        UniqueConstraint("provider", "provider_player_id"),
        CheckConstraint("username = lower(username)", name="username_lowercase"),
        CheckConstraint("char_length(username) > 0", name="username_not_empty"),
        CheckConstraint(
            "current_rapid_rating IS NULL OR current_rapid_rating >= 0",
            name="current_rapid_rating_non_negative",
        ),
        CheckConstraint(
            "current_rapid_rating_at IS NULL OR current_rapid_rating IS NOT NULL",
            name="current_rapid_rating_at_requires_rating",
        ),
    )

    provider: Mapped[Provider] = mapped_column(str_enum(Provider, "provider"), nullable=False)
    provider_player_id: Mapped[str | None] = mapped_column(String(64))
    username: Mapped[str] = mapped_column(String(USERNAME_MAX_LENGTH), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    profile_url: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    # Current Rapid rating from the provider's player stats, and the provider's
    # timestamp for that value. Distinct from ratings recorded on individual games.
    current_rapid_rating: Mapped[int | None] = mapped_column(Integer)
    current_rapid_rating_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    def __repr__(self) -> str:
        return f"Player(id={self.id!r}, provider={self.provider!r}, username={self.username!r})"
