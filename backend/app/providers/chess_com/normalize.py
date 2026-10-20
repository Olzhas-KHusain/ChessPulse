"""Validation and normalization of Chess.com PubAPI payloads.

Every payload is treated as untrusted. Rules:

* Required values that make a record meaningless when absent (game identifier,
  end time, time class, participants) exclude that record with a documented
  :class:`ExclusionReason`; other records are unaffected.
* Optional values that are missing or malformed become ``None`` and add an issue
  code; they are never replaced by invented defaults.
* Field meanings follow https://www.chess.com/news/view/published-data-api.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import unquote, urlsplit

from app.models.enums import GameResult, PlayerResult, Provider, TimeClass
from app.providers.chess_com.usernames import try_normalize_username
from app.providers.errors import ProviderError, ProviderErrorCode
from app.providers.types import (
    ArchiveIndex,
    ArchiveMonth,
    ExcludedGame,
    ExclusionReason,
    MonthArchive,
    ProviderGame,
    ProviderOpening,
    ProviderParticipant,
    ProviderProfile,
    ProviderStats,
    ResponseMeta,
)

PROVIDER = Provider.CHESS_COM
WEB_HOSTS = {"www.chess.com", "chess.com"}

MAX_PGN_CHARS = 100_000
MAX_URL_CHARS = 2048
MAX_RATING = 10_000
# Earliest plausible end time; guards against 0 / garbage epoch values.
MIN_PLAUSIBLE_TIME = datetime(2000, 1, 1, tzinfo=UTC)
FUTURE_TOLERANCE = timedelta(days=1)

# Documented result codes (PubAPI "Game results codes").
WIN_CODES = frozenset({"win"})
DRAW_CODES = frozenset(
    {"agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"}
)
LOSS_CODES = frozenset(
    {
        "checkmated",
        "timeout",
        "resigned",
        "lose",
        "abandoned",
        "kingofthehill",
        "threecheck",
        "bughousepartnerlose",
    }
)
KNOWN_RESULT_CODES = WIN_CODES | DRAW_CODES | LOSS_CODES

TIME_CLASSES = {tc.value: tc for tc in TimeClass}

_GAME_PATH_RE = re.compile(r"^/(?:game/(live|daily)|(live|daily)/game)/(\d{1,20})/?$")
_ARCHIVE_PATH_RE = re.compile(r"^/pub/player/([^/]+)/games/(\d{4})/(\d{2})/?$")
_OPENING_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-']{0,254}$")
_TIME_CONTROL_RE = re.compile(r"^\d{1,6}(?:[+/]\d{1,6})?$")
_RESULT_CODE_RE = re.compile(r"^[a-z0-9]{1,32}$")
_ECO_RE = re.compile(r"^[A-E][0-9]{2}$")
_PGN_HEADER_RE = re.compile(r'^\[([A-Za-z0-9_]+)\s+"((?:[^"\\]|\\.)*)"\]\s*$')
_STATUS_RE = re.compile(r"^[a-z_:]{1,64}$")


# --- small validators -------------------------------------------------------------


def _invalid(message: str) -> ProviderError:
    return ProviderError(ProviderErrorCode.UPSTREAM_INVALID_RESPONSE, message, status_code=200)


def epoch_to_utc(value: object) -> datetime | None:
    """Seconds since the Unix epoch -> aware UTC datetime; ``None`` if not a plausible int."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and (not math.isfinite(value) or not value.is_integer()):
        return None
    try:
        moment = datetime.fromtimestamp(int(value), tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None
    return moment if moment >= MIN_PLAUSIBLE_TIME else None


def _rating(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 <= value <= MAX_RATING else None


def _https_url(value: object, hosts: set[str]) -> str | None:
    if not isinstance(value, str) or not value or len(value) > MAX_URL_CHARS:
        return None
    parts = urlsplit(value)
    if parts.scheme != "https" or parts.hostname is None:
        return None
    if hosts and parts.hostname not in hosts:
        return None
    return value


def _clean_text(value: object, max_len: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > max_len or any(ord(ch) < 32 for ch in text):
        return None
    return text


def parse_game_id(url: object) -> str | None:
    """Stable game key from a game URL.

    Supported forms: ``/game/live/<id>``, ``/game/daily/<id>`` and the legacy
    ``/live/game/<id>``, ``/daily/game/<id>`` on www.chess.com. The key is
    ``"<namespace>:<id>"`` so that URL host or path changes do not create duplicates.
    """
    if _https_url(url, WEB_HOSTS) is None:
        return None
    assert isinstance(url, str)
    match = _GAME_PATH_RE.fullmatch(urlsplit(url).path)
    if match is None:
        return None
    namespace = match.group(1) or match.group(2)
    return f"{namespace}:{int(match.group(3))}"


def parse_opening_url(url: object) -> tuple[str, str] | None:
    """``(slug, display name)`` from a ``https://www.chess.com/openings/<slug>`` URL."""
    if _https_url(url, WEB_HOSTS) is None:
        return None
    assert isinstance(url, str)
    path = urlsplit(url).path
    prefix = "/openings/"
    if not path.startswith(prefix):
        return None
    slug = unquote(path[len(prefix) :]).strip("/")
    if not _OPENING_SLUG_RE.fullmatch(slug):
        return None
    return slug, slug.replace("-", " ")


def parse_pgn_headers(pgn: str) -> dict[str, str]:
    """Tag pairs from the PGN header section (stops at the first non-tag line)."""
    headers: dict[str, str] = {}
    for line in pgn.splitlines():
        stripped = line.strip()
        if not stripped:
            if headers:
                break
            continue
        match = _PGN_HEADER_RE.fullmatch(stripped)
        if match is None:
            break
        headers.setdefault(match.group(1), match.group(2).replace('\\"', '"'))
    return headers


def side_outcome(code: str | None) -> PlayerResult:
    if code in WIN_CODES:
        return PlayerResult.WIN
    if code in DRAW_CODES:
        return PlayerResult.DRAW
    if code in LOSS_CODES:
        return PlayerResult.LOSS
    return PlayerResult.UNKNOWN


def game_result(white: PlayerResult, black: PlayerResult) -> GameResult:
    """Combine per-side outcomes; inconsistent or unknown combinations stay UNKNOWN."""
    if white is PlayerResult.WIN and black is PlayerResult.LOSS:
        return GameResult.WHITE_WIN
    if black is PlayerResult.WIN and white is PlayerResult.LOSS:
        return GameResult.BLACK_WIN
    if white is PlayerResult.DRAW and black is PlayerResult.DRAW:
        return GameResult.DRAW
    return GameResult.UNKNOWN


# --- profile & stats ----------------------------------------------------------


def normalize_profile(payload: Mapping[str, Any], meta: ResponseMeta) -> ProviderProfile:
    issues: list[str] = []
    username = try_normalize_username(payload.get("username"))
    if username is None:
        raise _invalid("The provider profile has no valid username.")

    player_id_raw = payload.get("player_id")
    player_id: str | None = None
    if isinstance(player_id_raw, int) and not isinstance(player_id_raw, bool) and player_id_raw > 0:
        player_id = str(player_id_raw)
    elif player_id_raw is not None:
        issues.append("player_id_invalid")

    def optional(key: str, value: str | None) -> str | None:
        if value is None and payload.get(key) is not None:
            issues.append(f"{key}_invalid")
        return value

    status_raw = payload.get("status")
    status = (
        status_raw if isinstance(status_raw, str) and _STATUS_RE.fullmatch(status_raw) else None
    )
    return ProviderProfile(
        provider=PROVIDER,
        username=username,
        provider_player_id=player_id,
        display_name=optional("name", _clean_text(payload.get("name"), 255)),
        profile_url=optional("url", _https_url(payload.get("url"), WEB_HOSTS)),
        avatar_url=optional("avatar", _https_url(payload.get("avatar"), set())),
        account_status=optional("status", status),
        meta=meta,
        issues=tuple(issues),
    )


def normalize_stats(payload: Mapping[str, Any], meta: ResponseMeta) -> ProviderStats:
    section = payload.get("chess_rapid")
    if section is None:
        return ProviderStats(
            rapid_section_present=False, rapid_rating=None, rapid_rating_at=None, meta=meta
        )
    issues: list[str] = []
    last = section.get("last") if isinstance(section, dict) else None
    if not isinstance(last, dict):
        issues.append("chess_rapid_last_missing")
        last = {}
    rating = _rating(last.get("rating"))
    if rating is None and last:
        issues.append("chess_rapid_rating_invalid")
    rated_at = epoch_to_utc(last.get("date"))
    if rated_at is None and last.get("date") is not None:
        issues.append("chess_rapid_date_invalid")
    return ProviderStats(
        rapid_section_present=True,
        rapid_rating=rating,
        rapid_rating_at=rated_at if rating is not None else None,
        meta=meta,
        issues=tuple(issues),
    )


# --- archives -----------------------------------------------------------------


def normalize_archive_index(
    payload: Mapping[str, Any], username: str, meta: ResponseMeta
) -> ArchiveIndex:
    """Parse the archive list. URLs are only *read* for their year/month; requests are
    always built from validated values, never by following URLs from the payload."""
    raw = payload.get("archives")
    if not isinstance(raw, list):
        raise _invalid("The provider archive list is missing or not a list.")
    months: set[ArchiveMonth] = set()
    invalid = 0
    for item in raw:
        month = _archive_month_from_url(item, username)
        if month is None:
            invalid += 1
        else:
            months.add(month)
    issues = (f"archive_urls_ignored:{invalid}",) if invalid else ()
    return ArchiveIndex(months=tuple(sorted(months)), meta=meta, issues=issues)


def _archive_month_from_url(value: object, username: str) -> ArchiveMonth | None:
    if not isinstance(value, str) or len(value) > MAX_URL_CHARS:
        return None
    parts = urlsplit(value)
    if parts.scheme != "https" or parts.hostname != "api.chess.com":
        return None
    match = _ARCHIVE_PATH_RE.fullmatch(parts.path)
    if match is None or try_normalize_username(unquote(match.group(1))) != username:
        return None
    try:
        return ArchiveMonth(int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def normalize_month_archive(
    payload: Mapping[str, Any], username: str, month: ArchiveMonth, meta: ResponseMeta
) -> MonthArchive:
    raw_games = payload.get("games")
    if not isinstance(raw_games, list):
        raise _invalid("The provider monthly archive has no games list.")

    games: list[ProviderGame] = []
    excluded: list[ExcludedGame] = []
    seen: set[str] = set()
    latest_allowed = meta.fetched_at + FUTURE_TOLERANCE
    for index, item in enumerate(raw_games):
        outcome = normalize_game(item, owner=username, latest_allowed=latest_allowed)
        if isinstance(outcome, ExcludedGame):
            excluded.append(ExcludedGame(index, outcome.reason, outcome.provider_game_id))
        elif outcome.provider_game_id in seen:
            excluded.append(
                ExcludedGame(index, ExclusionReason.DUPLICATE_IN_ARCHIVE, outcome.provider_game_id)
            )
        else:
            seen.add(outcome.provider_game_id)
            games.append(outcome)
    return MonthArchive(
        username=username,
        month=month,
        games=tuple(games),
        excluded=tuple(excluded),
        meta=meta,
    )


# --- single game ----------------------------------------------------------------


def normalize_game(
    item: object, *, owner: str, latest_allowed: datetime
) -> ProviderGame | ExcludedGame:
    """Normalize one archive entry or explain why it was excluded.

    ``ExcludedGame.index`` is set to 0 here; the archive normalizer fills the position.
    """
    if not isinstance(item, dict):
        return ExcludedGame(0, ExclusionReason.NOT_AN_OBJECT)

    game_url = item.get("url")
    game_id = parse_game_id(game_url)
    if game_id is None:
        return ExcludedGame(0, ExclusionReason.MISSING_GAME_IDENTIFIER)
    assert isinstance(game_url, str)

    def exclude(reason: ExclusionReason) -> ExcludedGame:
        return ExcludedGame(0, reason, game_id)

    if item.get("end_time") is None:
        return exclude(ExclusionReason.MISSING_END_TIME)
    played_at = epoch_to_utc(item.get("end_time"))
    if played_at is None or played_at > latest_allowed:
        return exclude(ExclusionReason.INVALID_END_TIME)

    time_class = TIME_CLASSES.get(item.get("time_class"))  # type: ignore[arg-type]
    if time_class is None:
        return exclude(ExclusionReason.UNKNOWN_TIME_CLASS)

    issues: list[str] = []
    sides: dict[str, ProviderParticipant] = {}
    for color in ("white", "black"):
        side = item.get(color)
        if not isinstance(side, dict) or side.get("username") is None:
            return exclude(ExclusionReason.MISSING_PARTICIPANT)
        username = try_normalize_username(side.get("username"))
        if username is None:
            return exclude(ExclusionReason.INVALID_PARTICIPANT)
        rating = _rating(side.get("rating"))
        if rating is None and side.get("rating") is not None:
            issues.append(f"{color}_rating_invalid")
        code_raw = side.get("result")
        code = (
            code_raw if isinstance(code_raw, str) and _RESULT_CODE_RE.fullmatch(code_raw) else None
        )
        if code is None or code not in KNOWN_RESULT_CODES:
            issues.append(f"{color}_result_unrecognized")
        sides[color] = ProviderParticipant(
            username=username, rating=rating, result_code=code, outcome=side_outcome(code)
        )
    white, black = sides["white"], sides["black"]
    if white.username == black.username:
        return exclude(ExclusionReason.INVALID_PARTICIPANT)
    if owner not in (white.username, black.username):
        return exclude(ExclusionReason.OWNER_NOT_PARTICIPANT)

    result = game_result(white.outcome, black.outcome)
    if (
        result is GameResult.UNKNOWN
        and white.outcome is not PlayerResult.UNKNOWN
        and black.outcome is not PlayerResult.UNKNOWN
    ):
        issues.append("result_codes_inconsistent")

    rated_raw = item.get("rated")
    rated = rated_raw if isinstance(rated_raw, bool) else None
    if rated is None and rated_raw is not None:
        issues.append("rated_invalid")

    tc_raw = item.get("time_control")
    time_control = (
        tc_raw if isinstance(tc_raw, str) and _TIME_CONTROL_RE.fullmatch(tc_raw) else None
    )
    if time_control is None and tc_raw is not None:
        issues.append("time_control_invalid")

    rules_raw = item.get("rules")
    rules = (
        rules_raw if isinstance(rules_raw, str) and _RESULT_CODE_RE.fullmatch(rules_raw) else None
    )
    if rules is None and rules_raw is not None:
        issues.append("rules_invalid")

    pgn_raw = item.get("pgn")
    pgn: str | None = None
    headers: dict[str, str] = {}
    if isinstance(pgn_raw, str) and pgn_raw.strip():
        if len(pgn_raw) > MAX_PGN_CHARS:
            issues.append("pgn_too_large")
        else:
            pgn = pgn_raw
            headers = parse_pgn_headers(pgn_raw)
    elif pgn_raw is not None:
        issues.append("pgn_invalid")

    opening = _opening(item.get("eco"), headers, issues)

    return ProviderGame(
        provider=PROVIDER,
        provider_game_id=game_id,
        game_url=game_url,
        played_at=played_at,
        time_class=time_class,
        rules=rules,
        rated=rated,
        time_control=time_control,
        white=white,
        black=black,
        result=result,
        opening=opening,
        pgn=pgn,
        issues=tuple(issues),
    )


def _opening(
    eco_url: object, headers: Mapping[str, str], issues: list[str]
) -> ProviderOpening | None:
    """Opening from the game's ``eco`` URL, falling back to the PGN ``ECOUrl`` header.

    Without a provider opening identifier no opening is returned: an ECO code alone
    is not enough to identify the exact opening (spec §6.7).
    """
    parsed = parse_opening_url(eco_url)
    if parsed is None and eco_url is not None:
        issues.append("eco_url_unrecognized")
    if parsed is None and "ECOUrl" in headers:
        parsed = parse_opening_url(headers["ECOUrl"])
    if parsed is None:
        return None
    eco_header = headers.get("ECO")
    eco_code = eco_header if eco_header and _ECO_RE.fullmatch(eco_header) else None
    if eco_header and eco_code is None:
        issues.append("eco_code_invalid")
    slug, name = parsed
    return ProviderOpening(source_opening_id=slug, name=name, eco_code=eco_code)
