"""Persistence for ``players``."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Player, Provider
from app.repositories._batching import chunked, require_lowercase


@dataclass(frozen=True, slots=True)
class PlayerProfile:
    """Validated public profile data for one player.

    ``None`` means "the provider did not supply this field"; it is stored as NULL.
    """

    provider: Provider
    username: str
    provider_player_id: str | None = None
    display_name: str | None = None
    profile_url: str | None = None
    avatar_url: str | None = None


class PlayerRepository:
    """Data access for players. Methods never commit; the caller owns the transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_username(self, provider: Provider, username: str) -> Player | None:
        """Return the player with the normalized ``username``, if stored."""
        require_lowercase(username, "username")
        stmt = select(Player).where(Player.provider == provider, Player.username == username)
        return self._session.scalars(stmt).one_or_none()

    def ensure_usernames(self, provider: Provider, usernames: Iterable[str]) -> dict[str, int]:
        """Make sure a row exists for every username and return ``{username: id}``.

        Used for participants seen in game records. Existing rows are left untouched,
        so profile data fetched earlier is never overwritten with blanks.
        """
        unique = sorted(set(usernames))
        for username in unique:
            require_lowercase(username, "username")
        if not unique:
            return {}

        ids: dict[str, int] = {}
        for batch in chunked(unique):
            self._session.execute(
                insert(Player)
                .values([{"provider": provider, "username": name} for name in batch])
                .on_conflict_do_nothing(index_elements=[Player.provider, Player.username])
            )
            rows = self._session.execute(
                select(Player.username, Player.id).where(
                    Player.provider == provider, Player.username.in_(batch)
                )
            )
            ids.update({name: player_id for name, player_id in rows})
        return ids

    def upsert_profile(self, profile: PlayerProfile) -> Player:
        """Insert or update a player's profile fields and return the stored row.

        Profile fields are replaced as a whole: a field the provider no longer
        returns becomes NULL. Raises ``IntegrityError`` if ``provider_player_id``
        already belongs to a row with another username (a rename; see the schema doc).
        """
        require_lowercase(profile.username, "username")
        values = {
            "provider": profile.provider,
            "username": profile.username,
            "provider_player_id": profile.provider_player_id,
            "display_name": profile.display_name,
            "profile_url": profile.profile_url,
            "avatar_url": profile.avatar_url,
        }
        stmt = insert(Player).values(values)
        upsert = stmt.on_conflict_do_update(
            index_elements=[Player.provider, Player.username],
            set_={
                "provider_player_id": stmt.excluded.provider_player_id,
                "display_name": stmt.excluded.display_name,
                "profile_url": stmt.excluded.profile_url,
                "avatar_url": stmt.excluded.avatar_url,
                "updated_at": func.now(),
            },
        ).returning(Player)
        return self._session.scalars(upsert, execution_options={"populate_existing": True}).one()

    def get_by_provider_player_id(
        self, provider: Provider, provider_player_id: str
    ) -> Player | None:
        stmt = select(Player).where(
            Player.provider == provider, Player.provider_player_id == provider_player_id
        )
        return self._session.scalars(stmt).one_or_none()

    def rename(self, player_id: int, new_username: str) -> None:
        """Change a player's username after the provider confirmed a rename.

        Raises ``IntegrityError`` on flush if another row already uses ``new_username``.
        """
        require_lowercase(new_username, "username")
        player = self._session.get_one(Player, player_id)
        player.username = new_username
        self._session.flush()

    def set_current_rapid_rating(
        self, player_id: int, rating: int | None, observed_at: datetime | None
    ) -> None:
        """Store the provider's current Rapid rating (or clear it when unavailable)."""
        player = self._session.get_one(Player, player_id)
        player.current_rapid_rating = rating
        player.current_rapid_rating_at = observed_at
        self._session.flush()
