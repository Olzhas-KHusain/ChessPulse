"""End-to-end: HTTP API → cache → ingestion → real Chess.com adapter (mock transport)
→ PostgreSQL → analytics. Only the network is simulated; every other layer is real.

Fixture: tests/providers/fixtures/archive_mixed.json (synthetic, documented format).
Expected values below are calculated by hand from that file (see comments).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.providers.chess_com import ChessComHttpClient, ChessComProvider, RetryPolicy
from tests.db.conftest import Client
from tests.providers.conftest import load_fixture

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)  # window: 2026-09-01T12:00Z .. 2026-10-01T12:00Z
USER = "example_player"
BASE = f"/api/v1/players/{USER}"
API = f"https://api.chess.com/pub/player/{USER}"


def chess_com(handler: Callable[[httpx.Request], httpx.Response]) -> ChessComProvider:
    """The real adapter; only the transport is replaced. No sleeping in tests."""
    client = ChessComHttpClient(
        user_agent="ChessPulse-e2e (contact: tests@example.invalid)",
        retry=RetryPolicy(max_retries=1, max_delay_seconds=10),
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
        now=lambda: NOW,
    )
    return ChessComProvider(client)


def healthy(request: httpx.Request) -> httpx.Response:
    routes = {
        API: load_fixture("profile_full.json"),
        f"{API}/stats": load_fixture("stats_rapid.json"),
        f"{API}/games/archives": {"archives": [f"{API}/games/2026/09"]},
        f"{API}/games/2026/09": load_fixture("archive_mixed.json"),
    }
    payload = routes.get(str(request.url))
    return httpx.Response(200, json=payload) if payload is not None else httpx.Response(404)


def outage(request: httpx.Request) -> httpx.Response:
    return httpx.Response(503)


def rate_limited(request: httpx.Request) -> httpx.Response:
    return httpx.Response(429, headers={"Retry-After": "120"})


def timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("slow", request=request)


# Hand calculation from archive_mixed.json (14 entries) for window Sept 1 - Oct 1:
#   index 0  live:1000000001 rapid, rules=chess, owner White "win" vs "resigned"  -> WIN
#   index 1  blitz                                                   -> not_rapid
#   index 2  rapid, rules missing                                    -> rules_unverified
#   index 3  no url -> missing_game_identifier; 4 no end_time; 5 time_class "standard";
#   index 6  not an object; 7 duplicate of index 0; 8 owner absent; 9 missing white;
#   index 10 live:1000000010 rapid chess, owner White "mystery" vs "win" -> UNKNOWN
#   index 11 daily chess960 -> not_rapid; 12 invalid username; 13 end_time in 2030
# Eligible: index 10 (Sept 15) then index 0 (Sept 21) -> unknown, win.
EXPECTED_OVERVIEW = {
    "games_count": 2,
    "wins": 1,
    "losses": 0,
    "draws": 0,
    "unknown_results": 1,
    "win_rate": 100.0,  # 1 / (1 + 0 + 0) * 100; the unknown game is not in the denominator
    "current_streak": {"type": "win", "length": 1},
    "longest_winning_streak": 1,
    "streak_may_be_incomplete": True,  # an unknown result exists
    "current_rating": 1523,  # stats_rapid.json chess_rapid.last.rating
}


def _app(
    client: Client, handler: Callable[[httpx.Request], httpx.Response], now: datetime = NOW
) -> TestClient:
    return client(chess_com(handler), now)


def test_primary_flow_search_to_dashboard(client: Client) -> None:
    app = _app(client, healthy)

    overview = app.get(f"{BASE}/overview").json()
    assert {k: overview[k] for k in EXPECTED_OVERVIEW} == EXPECTED_OVERVIEW
    assert overview["data_status"] == "fresh"
    assert overview["period"] == {
        "start": "2026-09-01T12:00:00Z",
        "end": "2026-10-01T12:00:00Z",
        "timezone": "UTC",
    }

    games = app.get(f"{BASE}/games").json()
    assert [g["game_id"] for g in games["items"]] == ["live:1000000001", "live:1000000010"]
    detail = app.get(f"{BASE}/games/live:1000000001").json()
    assert detail["pgn"]["status"] == "available"
    assert detail["pgn"]["moves_san"] == ["e4", "c5", "Nf3", "d6"]
    assert detail["game"]["opening"]["name"] == "Sicilian Defense"

    openings = app.get(f"{BASE}/openings").json()
    assert {(i["name"], i["games_count"]) for i in openings["items"]} == {
        ("Sicilian Defense", 1),
        ("Unknown", 1),
    }
    opponents = app.get(f"{BASE}/opponents", params={"sort": "name"}).json()
    assert [i["opponent_username"] for i in opponents["items"]] == ["rival_five", "rival_one"]
    history = app.get(f"{BASE}/rating-history").json()
    assert [p["rating"] for p in history["points"]] == [1500, 1523]

    # Searching again with different casing hits the cache: no new upstream requests.
    calls: list[str] = []

    def counting(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return healthy(request)

    again = _app(client, counting).get("/api/v1/players/Example_Player/overview").json()
    assert calls == []
    assert again["games_count"] == 2


@pytest.mark.parametrize(
    ("handler", "code"),
    [
        (outage, "UPSTREAM_UNAVAILABLE"),
        (rate_limited, "UPSTREAM_RATE_LIMITED"),
        (timeout, "UPSTREAM_TIMEOUT"),
    ],
)
def test_provider_failure_keeps_last_known_good_data(
    client: Client, handler: Callable[[httpx.Request], httpx.Response], code: str
) -> None:
    _app(client, healthy).get(f"{BASE}/overview")
    later = NOW + timedelta(hours=13)  # TTL (12 h) expired

    stale = _app(client, handler, later).get(f"{BASE}/overview")
    assert stale.status_code == 200
    body = stale.json()
    assert body["data_status"] == "stale"
    assert body["refresh_error"] == code
    assert body["last_successful_update"] == "2026-10-01T12:00:00Z"
    assert body["games_count"] == 2  # not replaced by an empty dataset
    assert len(_app(client, handler, later).get(f"{BASE}/games").json()["items"]) == 2


@pytest.mark.parametrize(
    ("handler", "status", "code"),
    [
        (outage, 503, "UPSTREAM_UNAVAILABLE"),
        (rate_limited, 503, "UPSTREAM_RATE_LIMITED"),
        (timeout, 504, "UPSTREAM_TIMEOUT"),
    ],
)
def test_provider_failure_without_cache_is_an_error_not_empty_data(
    client: Client, handler: Callable[[httpx.Request], httpx.Response], status: int, code: str
) -> None:
    response = _app(client, handler).get(f"{BASE}/overview")
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert "games_count" not in response.text
    for leak in ("Traceback", "httpx", "psycopg", "api.chess.com", "postgresql"):
        assert leak not in response.text
    if code == "UPSTREAM_RATE_LIMITED":
        assert int(response.headers["Retry-After"]) >= 120  # provider Retry-After honoured


def test_confirmed_missing_player(client: Client) -> None:
    response = _app(client, lambda r: httpx.Response(404, json={"code": 0})).get(
        "/api/v1/players/does_not_exist/overview"
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PLAYER_NOT_FOUND"


def test_settings_defaults_are_safe() -> None:
    settings = Settings(_env_file=None, database_url="postgresql+psycopg://u:secret@h:5432/d")
    assert "secret" not in repr(settings)
    assert settings.cache_ttl_seconds == 12 * 3600
    assert settings.upstream_timeout_seconds <= 60
