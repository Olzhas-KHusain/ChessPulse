"""``GET /api/v1/players/{username}/overview`` end to end (test DB, fake provider)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.models import GameResult
from app.providers.errors import ProviderError, ProviderErrorCode
from app.providers.types import ArchiveMonth
from tests.db.conftest import Client
from tests.ingestion_helpers import NOW, OWNER, FakeProvider, game

pytestmark = pytest.mark.integration

OCT, SEPT = ArchiveMonth(2026, 10), ArchiveMonth(2026, 9)
URL = f"/api/v1/players/{OWNER}/overview"


def _games() -> FakeProvider:
    day = timedelta(days=1)
    return FakeProvider(
        months={
            OCT: [
                game(NOW - 5 * day, owner_color="white", result=GameResult.WHITE_WIN),
                game(NOW - 4 * day, owner_color="black", result=GameResult.WHITE_WIN),
                game(NOW - 3 * day, owner_color="black", result=GameResult.DRAW),
                game(NOW - 2 * day, owner_color="black", result=GameResult.BLACK_WIN),
                game(NOW - 1 * day, owner_color="white", result=GameResult.WHITE_WIN),
            ]
        }
    )


def test_overview_contract(client: Client) -> None:
    response = client(_games()).get(URL)
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "username": OWNER,
        "period": {
            "start": "2026-09-20T12:00:00Z",
            "end": "2026-10-20T12:00:00Z",
            "timezone": "UTC",
        },
        "games_count": 5,
        "wins": 3,
        "losses": 1,
        "draws": 1,
        "unknown_results": 0,
        "win_rate": 60.0,
        "current_rating": 1523,
        "current_rating_detail": {
            "rating": 1523,
            "as_of": "2026-10-20T12:00:00Z",
            "source": "provider_stats",
        },
        "current_streak": {"type": "win", "length": 2},
        "longest_winning_streak": 2,
        "streak_may_be_incomplete": False,
        "data_status": "fresh",
        "missing_sections": [],
        "refresh_error": None,
        "as_of": "2026-10-20T12:00:00Z",
        "last_successful_update": "2026-10-20T12:00:00Z",
    }


def test_zero_games_gives_null_win_rate_and_missing_rating(client: Client) -> None:
    body = client(FakeProvider(rapid_rating=None)).get(URL).json()
    assert body["games_count"] == 0
    assert body["win_rate"] is None
    assert body["current_streak"] is None
    assert body["longest_winning_streak"] is None
    assert body["current_rating"] is None and body["current_rating_detail"] is None
    assert body["missing_sections"] == ["current_rating"]
    assert body["data_status"] == "fresh"


def test_partial_dataset_is_flagged(client: Client) -> None:
    provider = _games()
    provider.months[SEPT] = ProviderError(ProviderErrorCode.UPSTREAM_TIMEOUT, "timeout")
    body = client(provider).get(URL).json()
    assert body["data_status"] == "partial"
    assert body["missing_sections"] == ["games"]
    assert body["streak_may_be_incomplete"] is True
    assert body["games_count"] == 5  # valid metrics still returned


def test_stale_data_after_failed_refresh(client: Client) -> None:
    client(_games()).get(URL)
    later = NOW + timedelta(hours=13)
    outage = FakeProvider(profile_error=ProviderError(ProviderErrorCode.UPSTREAM_UNAVAILABLE, "x"))
    body = client(outage, later).get(URL).json()
    assert body["data_status"] == "stale"
    assert body["refresh_error"] == "UPSTREAM_UNAVAILABLE"
    assert body["last_successful_update"] == "2026-10-20T12:00:00Z"
    assert body["as_of"] == "2026-10-21T01:00:00Z"
    # The window moved by 13 hours; all five games are still inside it.
    assert body["games_count"] == 5


def test_unknown_player_is_404_with_error_envelope(client: Client) -> None:
    provider = FakeProvider(profile_error=ProviderError(ProviderErrorCode.PLAYER_NOT_FOUND, "x"))
    response = client(provider).get(URL, headers={"X-Request-ID": "req-123"})
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "PLAYER_NOT_FOUND",
            "message": "No Chess.com player with this username.",
            "request_id": "req-123",
        }
    }


@pytest.mark.parametrize("username", ["bad.name", "x" * 65, "name%20with%20space"])
def test_invalid_username_is_rejected_without_upstream_calls(client: Client, username: str) -> None:
    provider = FakeProvider()
    response = client(provider).get(f"/api/v1/players/{username}/overview")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_USERNAME"
    assert provider.calls == []


def test_invalid_username_error_envelope(client: Client) -> None:
    response = client(FakeProvider()).get("/api/v1/players/bad.name/overview")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_USERNAME"
    assert response.headers["X-Request-ID"] == response.json()["error"]["request_id"]


@pytest.mark.parametrize(
    ("code", "status"),
    [
        (ProviderErrorCode.UPSTREAM_UNAVAILABLE, 503),
        (ProviderErrorCode.UPSTREAM_TIMEOUT, 504),
        (ProviderErrorCode.UPSTREAM_INVALID_RESPONSE, 502),
        (ProviderErrorCode.UPSTREAM_RATE_LIMITED, 503),
    ],
)
def test_upstream_failure_without_cache(
    client: Client, code: ProviderErrorCode, status: int
) -> None:
    provider = FakeProvider(profile_error=ProviderError(code, "internal detail"))
    response = client(provider).get(URL)
    assert response.status_code == status
    error = response.json()["error"]
    assert error["code"] == code.value
    assert "internal detail" not in response.text
    assert int(response.headers["Retry-After"]) == 300  # failure cooldown
