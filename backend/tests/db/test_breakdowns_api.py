"""Rating-history, openings and opponents endpoints end to end."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.models import GameResult, TimeClass
from app.providers.errors import ProviderError, ProviderErrorCode
from app.providers.types import ArchiveMonth, ProviderOpening
from tests.db.conftest import Client
from tests.ingestion_helpers import NOW, OWNER, FakeProvider, game

pytestmark = pytest.mark.integration

OCT, SEPT = ArchiveMonth(2026, 10), ArchiveMonth(2026, 9)
DAY = timedelta(days=1)
BASE = f"/api/v1/players/{OWNER}"
SICILIAN = ProviderOpening("Sicilian-Defense", "Sicilian Defense", "B20")
FRENCH = ProviderOpening("French-Defense", "French Defense", "C00")


def _provider() -> FakeProvider:
    return FakeProvider(
        months={
            OCT: [
                game(NOW - 5 * DAY, opponent="alpha", opening=SICILIAN, white_rating=1500),
                game(
                    NOW - 4 * DAY,
                    opponent="alpha",
                    opening=SICILIAN,
                    owner_color="black",
                    result=GameResult.WHITE_WIN,
                    black_rating=1492,
                ),
                game(NOW - 3 * DAY, opponent="alpha-1", opening=FRENCH, result=GameResult.DRAW),
                game(NOW - 2 * DAY, opponent="beta", white_rating=None, result=GameResult.UNKNOWN),
                # Out of scope: Blitz, and a game before the window.
                game(NOW - 1 * DAY, opponent="gamma", time_class=TimeClass.BLITZ),
            ],
            SEPT: [game(NOW - 40 * DAY, opponent="delta")],
        }
    )


def test_rating_history(client: Client) -> None:
    body = client(_provider()).get(f"{BASE}/rating-history").json()
    assert [(p["rating"], p["source"]) for p in body["points"]] == [
        (1500, "game_record"),
        (1492, "game_record"),
        (1500, "game_record"),
    ]
    assert body["points"][0]["timestamp"] == "2026-10-15T12:00:00Z"
    assert body["coverage"] == "partial"  # one game without rating
    assert (body["games_considered"], body["games_without_rating"]) == (4, 1)
    assert body["rating_semantics"] == "reported_with_game"
    assert body["data_status"] == "fresh"


def test_rating_history_from_to_narrow_the_window(client: Client) -> None:
    c = client(_provider())
    body = c.get(
        f"{BASE}/rating-history",
        params={"from": "2026-10-15T12:00:01Z", "to": "2026-10-17T12:00:01Z"},
    ).json()
    assert [p["rating"] for p in body["points"]] == [1492, 1500]
    assert body["period"] == {
        "start": "2026-10-15T12:00:01Z",
        "end": "2026-10-17T12:00:01Z",
        "timezone": "UTC",
    }
    wide = c.get(f"{BASE}/rating-history", params={"from": "2020-01-01T00:00:00Z"}).json()
    assert wide["period"]["start"] == "2026-09-20T12:00:00Z"  # never wider than 30 days


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-10-18T00:00:00Z", "to": "2026-10-17T00:00:00Z"},
        {"from": "2026-10-18T00:00:00"},  # no time zone
        {"from": "yesterday"},
    ],
)
def test_rating_history_parameter_validation(client: Client, params: dict[str, str]) -> None:
    response = client(FakeProvider()).get(f"{BASE}/rating-history", params=params)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PARAMETER"


def test_openings(client: Client) -> None:
    body = client(_provider()).get(f"{BASE}/openings").json()
    assert body["sort"] == "games" and body["total_groups"] == 3
    items = {i["name"]: i for i in body["items"]}
    assert items["Sicilian Defense"] | {} == {
        "opening_key": "Sicilian-Defense",
        "name": "Sicilian Defense",
        "eco_code": "B20",
        "is_unknown": False,
        "games_count": 2,
        "wins": 1,
        "losses": 1,
        "draws": 0,
        "unknown_results": 0,
        "win_rate": 50.0,
    }
    unknown = items["Unknown"]
    assert unknown["is_unknown"] and unknown["opening_key"] is None
    assert (unknown["games_count"], unknown["unknown_results"], unknown["win_rate"]) == (1, 1, None)
    assert body["items"][0]["name"] == "Sicilian Defense"  # largest sample first


def test_opponents_keep_similar_names_apart(client: Client) -> None:
    body = client(_provider()).get(f"{BASE}/opponents", params={"sort": "name"}).json()
    assert body["perspective"] == "searched_player"
    assert [(i["opponent_username"], i["games_count"]) for i in body["items"]] == [
        ("alpha", 2),
        ("alpha-1", 1),
        ("beta", 1),
    ]
    alpha = body["items"][0]
    assert (alpha["wins"], alpha["losses"], alpha["win_rate"]) == (1, 1, 50.0)
    assert alpha["last_played_at"] == "2026-10-16T12:00:00Z"
    assert alpha["last_rating"] == 1500  # alpha played White in that game
    assert alpha["profile_url"] == "https://www.chess.com/member/alpha"


def test_limit_truncates_but_reports_total(client: Client) -> None:
    body = client(_provider()).get(f"{BASE}/opponents", params={"limit": 1}).json()
    assert len(body["items"]) == 1 and body["total_groups"] == 3


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("openings", {"limit": 0}),
        ("openings", {"limit": 101}),
        ("opponents", {"limit": "many"}),
        ("opponents", {"sort": "random"}),
    ],
)
def test_query_validation(client: Client, path: str, params: dict[str, str | int]) -> None:
    provider = FakeProvider()
    response = client(provider).get(f"{BASE}/{path}", params=params)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "INVALID_PARAMETER"
    assert "random" not in error["message"] and "many" not in error["message"]


def test_zero_games_gives_empty_groups(client: Client) -> None:
    c = client(FakeProvider())
    assert c.get(f"{BASE}/openings").json()["items"] == []
    assert c.get(f"{BASE}/opponents").json()["total_groups"] == 0
    history = c.get(f"{BASE}/rating-history").json()
    assert history["points"] == [] and history["coverage"] == "none"


def test_partial_dataset_is_reported(client: Client) -> None:
    provider = _provider()
    provider.months[SEPT] = ProviderError(ProviderErrorCode.UPSTREAM_TIMEOUT, "t")
    c = client(provider)
    assert c.get(f"{BASE}/openings").json()["data_status"] == "partial"
    history = c.get(f"{BASE}/rating-history").json()
    assert history["data_status"] == "partial" and history["coverage"] == "partial"
    assert history["refresh_error"] == "INGESTION_INCOMPLETE"


def test_unknown_player_is_404(client: Client) -> None:
    provider = FakeProvider(profile_error=ProviderError(ProviderErrorCode.PLAYER_NOT_FOUND, "x"))
    assert client(provider).get(f"{BASE}/openings").status_code == 404
