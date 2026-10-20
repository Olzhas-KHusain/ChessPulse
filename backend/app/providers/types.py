"""Normalized, provider-independent domain types returned by provider adapters.

Conventions:

* ``None`` always means "the provider did not supply a usable value". No field is
  ever filled with a default that could be mistaken for real data.
* ``issues`` lists non-fatal data-quality notes (for example ``white_rating_invalid``)
  so callers can report partial data without failing the whole record.
* All datetimes are timezone-aware UTC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.models.enums import GameResult, PlayerResult, Provider, TimeClass


@dataclass(frozen=True, slots=True)
class ResponseMeta:
    """Transport metadata for one successful upstream response."""

    fetched_at: datetime
    etag: str | None = None
    last_modified: str | None = None
    # Cache-Control max-age in seconds, when the provider sent one.
    max_age_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class ProviderProfile:
    """Public profile of one player."""

    provider: Provider
    username: str  # normalized (lowercase)
    provider_player_id: str | None
    display_name: str | None
    profile_url: str | None
    avatar_url: str | None
    # Raw provider account status, e.g. "basic", "premium", "closed",
    # "closed:fair_play_violations". Kept for later product decisions; not interpreted here.
    account_status: str | None
    meta: ResponseMeta
    issues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderStats:
    """Current Rapid rating from the provider's player statistics."""

    # False when the provider has no Rapid section for the player (never rated in Rapid).
    rapid_section_present: bool
    rapid_rating: int | None
    # Provider timestamp of the last rated Rapid game that produced ``rapid_rating``.
    rapid_rating_at: datetime | None
    meta: ResponseMeta
    issues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, order=True)
class ArchiveMonth:
    """One monthly game archive. The provider groups games by the month the game ended."""

    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise ValueError("month must be between 1 and 12")
        if not 2000 <= self.year <= 9999:
            raise ValueError("year is out of range")

    @property
    def start(self) -> datetime:
        return datetime(self.year, self.month, 1, tzinfo=UTC)

    @property
    def end(self) -> datetime:
        """Exclusive upper bound (first instant of the next month, UTC)."""
        if self.month == 12:
            return datetime(self.year + 1, 1, 1, tzinfo=UTC)
        return datetime(self.year, self.month + 1, 1, tzinfo=UTC)

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


@dataclass(frozen=True, slots=True)
class ArchiveIndex:
    """Monthly archives available for a player, oldest first."""

    months: tuple[ArchiveMonth, ...]
    meta: ResponseMeta
    issues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderParticipant:
    username: str  # normalized (lowercase)
    # Rating exactly as reported in the game record; the provider does not document
    # whether it is the pre-game or post-game value.
    rating: int | None
    # Raw provider result code for this side, e.g. "win", "resigned", "agreed".
    result_code: str | None
    outcome: PlayerResult


@dataclass(frozen=True, slots=True)
class ProviderOpening:
    """Opening identified by the provider's opening page."""

    source_opening_id: str  # URL slug of the provider's opening page
    name: str  # display name derived from the slug (hyphens shown as spaces)
    eco_code: str | None  # from the PGN "ECO" header, when present and well-formed


@dataclass(frozen=True, slots=True)
class ProviderGame:
    """One completed game from a monthly archive."""

    provider: Provider
    provider_game_id: str  # stable key, e.g. "live:123456789"
    game_url: str
    played_at: datetime  # game end time
    time_class: TimeClass
    rules: str | None  # provider variant, e.g. "chess", "chess960"
    rated: bool | None
    time_control: str | None
    white: ProviderParticipant
    black: ProviderParticipant
    result: GameResult
    opening: ProviderOpening | None
    pgn: str | None
    issues: tuple[str, ...] = ()

    @property
    def is_standard_chess(self) -> bool:
        """True only when the provider explicitly marks the game as standard chess."""
        return self.rules == "chess"

    def participant(self, username: str) -> ProviderParticipant | None:
        if self.white.username == username:
            return self.white
        if self.black.username == username:
            return self.black
        return None


class ExclusionReason(StrEnum):
    """Why a record from an archive could not be normalized."""

    NOT_AN_OBJECT = "not_an_object"
    MISSING_GAME_IDENTIFIER = "missing_game_identifier"
    MISSING_END_TIME = "missing_end_time"
    INVALID_END_TIME = "invalid_end_time"
    UNKNOWN_TIME_CLASS = "unknown_time_class"
    MISSING_PARTICIPANT = "missing_participant"
    INVALID_PARTICIPANT = "invalid_participant"
    OWNER_NOT_PARTICIPANT = "owner_not_participant"
    DUPLICATE_IN_ARCHIVE = "duplicate_in_archive"


@dataclass(frozen=True, slots=True)
class ExcludedGame:
    """A record that was skipped, with a documented reason (no raw payload is kept)."""

    index: int  # position in the provider's "games" array
    reason: ExclusionReason
    provider_game_id: str | None = None


@dataclass(frozen=True, slots=True)
class MonthArchive:
    """Normalized content of one monthly archive.

    An archive with no games and no exclusions is a confirmed empty result.
    """

    username: str
    month: ArchiveMonth
    games: tuple[ProviderGame, ...]
    excluded: tuple[ExcludedGame, ...]
    meta: ResponseMeta
    issues: tuple[str, ...] = field(default=())
