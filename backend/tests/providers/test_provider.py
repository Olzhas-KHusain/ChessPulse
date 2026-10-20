"""End-to-end adapter behavior with mocked responses: profile, stats, archives, games."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from app.core.config import ConfigurationError, Settings, load_settings
from app.models import GameResult, PlayerResult, Provider, TimeClass
from app.providers.chess_com import (
    ChessComProvider,
    InvalidUsernameError,
    normalize_username,
    select_archive_months,
)
from app.providers.errors import ProviderError, ProviderErrorCode
from app.providers.types import ArchiveMonth, ExclusionReason, MonthArchive
from tests.providers.conftest import Harness, json_response, load_fixture, routes, sequence

BASE = "/pub/player/example_player"
SEPT = ArchiveMonth(2026, 9)


def _provider(path: str, payload: object, status: int = 200) -> ChessComProvider:
    return Harness(routes({path: json_response(status, payload)})).provider()


def _mixed_archive() -> MonthArchive:
    return _provider(f"{BASE}/games/2026/09", load_fixture("archive_mixed.json")).get_month_archive(
        "example_player", SEPT
    )


# --- profile ------------------------------------------------------------------------


def test_profile_is_normalized() -> None:
    profile = _provider(BASE, load_fixture("profile_full.json")).get_profile("example_player")
    assert profile.provider is Provider.CHESS_COM
    assert profile.username == "example_player"
    assert profile.provider_player_id == "123456"
    assert profile.display_name == "Example Player"
    assert profile.profile_url == "https://www.chess.com/member/Example_Player"
    assert profile.avatar_url is not None and profile.avatar_url.startswith("https://images.")
    assert profile.account_status == "premium"
    assert profile.issues == ()


def test_profile_missing_optional_fields_stay_none() -> None:
    profile = _provider(BASE, load_fixture("profile_minimal.json")).get_profile("example_player")
    assert profile.provider_player_id == "123456"
    assert (profile.display_name, profile.profile_url, profile.avatar_url) == (None, None, None)
    assert profile.account_status is None
    assert profile.issues == ()


def test_profile_malformed_optional_fields_become_none_with_issues() -> None:
    payload = {
        "username": "example_player",
        "player_id": "not-a-number",
        "name": "",
        "url": "http://www.chess.com/member/x",
        "avatar": "javascript:alert(1)",
        "status": 7,
    }
    profile = _provider(BASE, payload).get_profile("example_player")
    assert profile.provider_player_id is None
    assert (profile.display_name, profile.profile_url, profile.avatar_url) == (None, None, None)
    assert set(profile.issues) == {
        "player_id_invalid",
        "name_invalid",
        "url_invalid",
        "avatar_invalid",
        "status_invalid",
    }


def test_confirmed_missing_player() -> None:
    provider = _provider(BASE.replace("example_player", "does_not_exist"), {}, status=404)
    with pytest.raises(ProviderError) as excinfo:
        provider.get_profile("does_not_exist")
    assert excinfo.value.code is ProviderErrorCode.PLAYER_NOT_FOUND


@pytest.mark.parametrize("username", ["", "   ", "a/b", "../etc", "name with space", "é", "x" * 65])
def test_invalid_usernames_never_reach_the_network(username: str) -> None:
    harness = Harness(sequence())
    with pytest.raises(InvalidUsernameError):
        harness.provider().get_profile(username)
    assert harness.requests == []


@pytest.mark.parametrize(("raw", "expected"), [("  Hikaru ", "hikaru"), ("a-b_c9", "a-b_c9")])
def test_normalize_username(raw: str, expected: str) -> None:
    assert normalize_username(raw) == expected


# --- stats ----------------------------------------------------------------------------


def test_stats_with_rapid_section() -> None:
    stats = _provider(f"{BASE}/stats", load_fixture("stats_rapid.json")).get_stats("example_player")
    assert stats.rapid_section_present
    assert stats.rapid_rating == 1523
    assert stats.rapid_rating_at == datetime(2026, 9, 21, 14, 13, 20, tzinfo=UTC)
    assert stats.issues == ()


def test_stats_without_rapid_is_unknown_not_zero() -> None:
    stats = _provider(f"{BASE}/stats", load_fixture("stats_no_rapid.json")).get_stats(
        "example_player"
    )
    assert not stats.rapid_section_present
    assert stats.rapid_rating is None
    assert stats.rapid_rating_at is None


@pytest.mark.parametrize(
    ("section", "issue"),
    [
        ({"last": {"rating": "1500", "date": 1790000000}}, "chess_rapid_rating_invalid"),
        ({"last": {"rating": -5, "date": 1790000000}}, "chess_rapid_rating_invalid"),
        ({"record": {"win": 1}}, "chess_rapid_last_missing"),
        ("garbage", "chess_rapid_last_missing"),
    ],
)
def test_stats_malformed_rating_is_none(section: object, issue: str) -> None:
    stats = _provider(f"{BASE}/stats", {"chess_rapid": section}).get_stats("example_player")
    assert stats.rapid_section_present
    assert stats.rapid_rating is None and stats.rapid_rating_at is None
    assert issue in stats.issues


def test_stats_with_invalid_date_keeps_rating_without_timestamp() -> None:
    stats = _provider(
        f"{BASE}/stats", {"chess_rapid": {"last": {"rating": 1500, "date": "yesterday"}}}
    ).get_stats("example_player")
    assert stats.rapid_rating == 1500
    assert stats.rapid_rating_at is None
    assert stats.issues == ("chess_rapid_date_invalid",)


# --- archive list -------------------------------------------------------------------


def test_archive_list_keeps_only_valid_months_of_this_player() -> None:
    index = _provider(f"{BASE}/games/archives", load_fixture("archives.json")).list_archive_months(
        "example_player"
    )
    assert [str(m) for m in index.months] == ["2026-08", "2026-09", "2026-10"]
    assert index.issues == ("archive_urls_ignored:5",)


def test_archive_list_without_list_is_invalid() -> None:
    with pytest.raises(ProviderError) as excinfo:
        _provider(f"{BASE}/games/archives", {"archives": "nope"}).list_archive_months(
            "example_player"
        )
    assert excinfo.value.code is ProviderErrorCode.UPSTREAM_INVALID_RESPONSE


def test_player_without_archives_is_a_valid_empty_list() -> None:
    index = _provider(f"{BASE}/games/archives", {"archives": []}).list_archive_months(
        "example_player"
    )
    assert index.months == ()


def test_select_archive_months_for_window() -> None:
    available = [ArchiveMonth(2026, m) for m in (6, 8, 9, 10)]
    start = datetime(2026, 9, 20, 10, tzinfo=UTC)
    end = datetime(2026, 10, 20, 10, tzinfo=UTC)
    assert select_archive_months(available, start, end) == [
        ArchiveMonth(2026, 9),
        ArchiveMonth(2026, 10),
    ]
    # A window starting on the 1st also includes the previous month (time-zone margin).
    early = datetime(2026, 9, 1, 0, 30, tzinfo=UTC)
    assert ArchiveMonth(2026, 8) in select_archive_months(available, early, end)
    with pytest.raises(ValueError):
        select_archive_months(available, end, start)


def test_archive_month_bounds() -> None:
    assert ArchiveMonth(2026, 12).end == datetime(2027, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError):
        ArchiveMonth(2026, 13)


# --- monthly archive -------------------------------------------------------------------


def test_empty_archive_is_a_confirmed_empty_result() -> None:
    archive = _provider(
        f"{BASE}/games/2026/09", load_fixture("archive_empty.json")
    ).get_month_archive("example_player", SEPT)
    assert archive.games == () and archive.excluded == ()


@pytest.mark.parametrize("payload", [{}, {"games": None}, {"games": {"0": {}}}])
def test_archive_without_games_list_is_invalid_not_empty(payload: object) -> None:
    with pytest.raises(ProviderError) as excinfo:
        _provider(f"{BASE}/games/2026/09", payload).get_month_archive("example_player", SEPT)
    assert excinfo.value.code is ProviderErrorCode.UPSTREAM_INVALID_RESPONSE


def test_mixed_archive_keeps_valid_games_and_explains_exclusions() -> None:
    archive = _mixed_archive()
    assert [g.provider_game_id for g in archive.games] == [
        "live:1000000001",
        "live:1000000002",
        "live:1000000003",
        "live:1000000010",
        "daily:1000000011",
    ]
    assert [(e.index, e.reason, e.provider_game_id) for e in archive.excluded] == [
        (3, ExclusionReason.MISSING_GAME_IDENTIFIER, None),
        (4, ExclusionReason.MISSING_END_TIME, "live:1000000005"),
        (5, ExclusionReason.UNKNOWN_TIME_CLASS, "live:1000000006"),
        (6, ExclusionReason.NOT_AN_OBJECT, None),
        (7, ExclusionReason.DUPLICATE_IN_ARCHIVE, "live:1000000001"),
        (8, ExclusionReason.OWNER_NOT_PARTICIPANT, "live:1000000008"),
        (9, ExclusionReason.MISSING_PARTICIPANT, "live:1000000009"),
        (12, ExclusionReason.INVALID_PARTICIPANT, "live:1000000012"),
        (13, ExclusionReason.INVALID_END_TIME, "live:1000000013"),
    ]


def test_complete_game_is_fully_normalized() -> None:
    game = _mixed_archive().games[0]
    assert game.game_url == "https://www.chess.com/game/live/1000000001"
    assert game.played_at == datetime(2026, 9, 21, 14, 13, 20, tzinfo=UTC)
    assert game.time_class is TimeClass.RAPID
    assert game.rules == "chess" and game.is_standard_chess
    assert game.rated is True
    assert game.time_control == "600+5"
    assert (game.white.username, game.white.rating, game.white.outcome) == (
        "example_player",
        1523,
        PlayerResult.WIN,
    )
    assert (game.black.username, game.black.result_code, game.black.outcome) == (
        "rival_one",
        "resigned",
        PlayerResult.LOSS,
    )
    assert game.result is GameResult.WHITE_WIN
    assert game.opening is not None
    assert game.opening.source_opening_id == "Sicilian-Defense"
    assert game.opening.name == "Sicilian Defense"
    assert game.opening.eco_code == "B20"
    assert game.pgn is not None and game.pgn.startswith("[Event")
    assert game.issues == ()
    assert game.participant("rival_one") is game.black


def test_legacy_url_draw_and_opening_without_pgn_eco() -> None:
    game = _mixed_archive().games[1]
    assert game.provider_game_id == "live:1000000002"
    assert game.time_class is TimeClass.BLITZ  # classified; Rapid filtering happens later
    assert game.result is GameResult.DRAW
    assert game.opening is not None and game.opening.eco_code is None


def test_missing_optional_fields_are_none_not_invented() -> None:
    game = _mixed_archive().games[2]
    assert game.rules is None and not game.is_standard_chess
    assert game.rated is None
    assert game.time_control is None
    assert game.pgn is None
    assert game.opening is None
    assert game.white.rating is None  # "1500" as a string is not trusted
    assert game.black.rating is None  # absent
    assert game.result is GameResult.WHITE_WIN
    assert game.issues == ("white_rating_invalid",)


def test_malformed_optional_fields_do_not_drop_the_game() -> None:
    game = _mixed_archive().games[3]
    assert game.result is GameResult.UNKNOWN
    assert game.white.outcome is PlayerResult.UNKNOWN
    assert game.rated is None and game.time_control is None and game.opening is None
    assert set(game.issues) == {
        "white_result_unrecognized",
        "rated_invalid",
        "time_control_invalid",
        "eco_url_unrecognized",
    }


def test_daily_variant_game_is_normalized_with_its_rules() -> None:
    game = _mixed_archive().games[4]
    assert game.provider_game_id == "daily:1000000011"
    assert game.time_class is TimeClass.DAILY
    assert game.rules == "chess960" and not game.is_standard_chess
    assert game.time_control == "1/259200"
    assert game.result is GameResult.BLACK_WIN


def test_month_archive_request_path_uses_validated_values() -> None:
    harness = Harness(routes({f"{BASE}/games/2026/03": json_response(200, {"games": []})}))
    harness.provider().get_month_archive("Example_Player", ArchiveMonth(2026, 3))
    assert (
        str(harness.requests[0].url)
        == "https://api.chess.com/pub/player/example_player/games/2026/03"
    )


# --- settings ----------------------------------------------------------------------


def test_provider_from_settings_uses_configuration() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://u:p@localhost:5432/db",
        chess_com_user_agent="ChessPulse/test (contact: ops@example.invalid)",
        upstream_max_retries=0,
    )
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(503)

    provider = ChessComProvider.from_settings(settings, transport=httpx.MockTransport(handler))
    with provider, pytest.raises(ProviderError):
        provider.get_profile("example_player")
    assert len(seen) == 1  # no retries configured
    assert seen[0].headers["user-agent"] == "ChessPulse/test (contact: ops@example.invalid)"


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("UPSTREAM_TIMEOUT_SECONDS", "0"),
        ("UPSTREAM_MAX_RETRIES", "9"),
        ("UPSTREAM_MAX_RETRY_AFTER_SECONDS", "-1"),
        ("CHESS_COM_USER_AGENT", "bad\u0007agent"),
    ],
)
def test_invalid_provider_settings_are_rejected(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    monkeypatch.setenv(variable, value)
    with pytest.raises(ConfigurationError, match=variable):
        load_settings(env_file=None)
