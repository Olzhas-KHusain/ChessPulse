"""Game list and game details endpoints end to end."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.models import GameResult, TimeClass
from app.providers.errors import ProviderError, ProviderErrorCode
from app.providers.types import ArchiveMonth, ProviderOpening
from app.services.games import encode_cursor
from tests.db.conftest import Client
from tests.ingestion_helpers import NOW, OWNER, FakeProvider, game

pytestmark = pytest.mark.integration

OCT, SEPT = ArchiveMonth(2026, 10), ArchiveMonth(2026, 9)
DAY = timedelta(days=1)
BASE = f"/api/v1/players/{OWNER}/games"
GOOD_PGN = (
    '[Event "Live Chess"]\n[White "example_player"]\n[ECO "C20"]\n\n1. e4 e5 2. Nf3 Nc6 1-0\n'
)
BAD_PGN = '[Event "Live Chess"]\n\n1. e4 e5 2. Ke3 Nf6 1-0\n'
SAME_TIME = NOW - 2 * DAY


def _provider() -> FakeProvider:
    return FakeProvider(
        months={
            OCT: [
                game(
                    NOW - 5 * DAY,
                    game_id="live:1",
                    result=GameResult.WHITE_WIN,
                    pgn=GOOD_PGN,
                    opening=ProviderOpening("Kings-Pawn", "Kings Pawn", "C20"),
                ),
                game(
                    NOW - 4 * DAY,
                    game_id="live:2",
                    owner_color="black",
                    result=GameResult.WHITE_WIN,
                    pgn=BAD_PGN,
                ),
                game(NOW - 3 * DAY, game_id="live:3", result=GameResult.DRAW),
                game(SAME_TIME, game_id="live:4", result=GameResult.UNKNOWN),
                game(SAME_TIME, game_id="live:5", result=GameResult.WHITE_WIN),
                game(NOW - 1 * DAY, game_id="live:6", time_class=TimeClass.BLITZ),
            ],
            SEPT: [game(NOW - 40 * DAY, game_id="live:7")],
        }
    )


def _ids(body: dict[str, object]) -> list[str]:
    return [item["game_id"] for item in body["items"]]  # type: ignore[attr-defined]


def test_list_contains_only_eligible_games_newest_first(client: Client) -> None:
    body = client(_provider()).get(BASE).json()
    # Equal timestamps: live:5 was stored after live:4, so its internal id is higher.
    assert _ids(body) == ["live:5", "live:4", "live:3", "live:2", "live:1"]
    assert body["next_cursor"] is None
    first = body["items"][-1]
    assert first == {
        "game_id": "live:1",
        "played_at": "2026-10-15T12:00:00Z",
        "result": "win",
        "color": "white",
        "player_rating": 1500,
        "opponent": {"username": "rival", "rating": 1490},
        "time_control": "600",
        "rated": True,
        "opening": {"opening_key": "Kings-Pawn", "name": "Kings Pawn", "eco_code": "C20"},
        "game_url": "https://www.chess.com/game/live/1",
    }
    assert body["items"][-2]["opening"] is None  # unknown opening stays null


def test_pages_are_deterministic_and_never_overlap(client: Client) -> None:
    c = client(_provider())
    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        params: dict[str, str | int] = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        body = c.get(BASE, params=params).json()
        seen += _ids(body)
        pages += 1
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert pages == 3
    assert seen == ["live:5", "live:4", "live:3", "live:2", "live:1"]
    again = c.get(BASE, params={"limit": 2}).json()
    assert _ids(again) == ["live:5", "live:4"]


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ("win", ["live:5", "live:1"]),
        ("loss", ["live:2"]),
        ("draw", ["live:3"]),
        ("unknown", ["live:4"]),
    ],
)
def test_result_filter(client: Client, result: str, expected: list[str]) -> None:
    body = client(_provider()).get(BASE, params={"result": result}).json()
    assert _ids(body) == expected
    assert body["result_filter"] == result


def test_filtered_pagination(client: Client) -> None:
    c = client(_provider())
    page1 = c.get(BASE, params={"result": "win", "limit": 1}).json()
    page2 = c.get(BASE, params={"result": "win", "limit": 1, "cursor": page1["next_cursor"]}).json()
    assert _ids(page1) + _ids(page2) == ["live:5", "live:1"]
    assert page2["next_cursor"] is None
    # A cursor issued for one filter is rejected for another.
    mismatch = c.get(BASE, params={"result": "loss", "cursor": page1["next_cursor"]})
    assert mismatch.status_code == 400


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"limit": "all"},
        {"result": "victory"},
        {"cursor": "not-a-cursor"},
        {"cursor": "x" * 300},
    ],
)
def test_bounded_and_validated_parameters(client: Client, params: dict[str, str | int]) -> None:
    response = client(FakeProvider()).get(BASE, params=params)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PARAMETER"


def test_empty_list(client: Client) -> None:
    body = client(FakeProvider()).get(BASE).json()
    assert body["items"] == [] and body["next_cursor"] is None
    assert body["data_status"] == "fresh"


def test_game_detail_with_parsed_pgn(client: Client) -> None:
    body = client(_provider()).get(f"{BASE}/live:1").json()
    assert body["game"]["game_id"] == "live:1"
    assert body["pgn"]["status"] == "available"
    assert body["pgn"]["moves_san"] == ["e4", "e5", "Nf3", "Nc6"]
    assert body["pgn"]["headers"]["ECO"] == "C20"
    assert body["pgn"]["raw"] == GOOD_PGN
    assert body["rating_semantics"] == "reported_with_game"


def test_missing_pgn_does_not_break_details(client: Client) -> None:
    body = client(_provider()).get(f"{BASE}/live:3").json()
    assert body["pgn"] == {
        "status": "missing",
        "headers": {},
        "moves_san": None,
        "error": None,
        "raw": None,
    }
    assert body["game"]["result"] == "draw"


def test_malformed_pgn_is_a_per_game_limitation(client: Client) -> None:
    c = client(_provider())
    bad = c.get(f"{BASE}/live:2").json()
    assert bad["pgn"]["status"] == "malformed"
    assert bad["pgn"]["error"] == "illegal_move"
    assert bad["pgn"]["moves_san"] is None
    assert bad["game"]["result"] == "loss"
    assert c.get(f"{BASE}/live:1").json()["pgn"]["status"] == "available"
    assert len(c.get(BASE).json()["items"]) == 5


@pytest.mark.parametrize("game_id", ["live:6", "live:7", "live:999", "x" * 200])
def test_ineligible_or_missing_game_is_404(client: Client, game_id: str) -> None:
    response = client(_provider()).get(f"{BASE}/{game_id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "GAME_NOT_FOUND"


def test_game_of_another_player_is_not_exposed(client: Client) -> None:
    c = client(_provider())
    c.get(BASE)  # ingest example_player
    other = FakeProvider(
        username="someone_else",
        player_id="999",
        months={OCT: []},
    )
    response = client(other).get("/api/v1/players/someone_else/games/live:1")
    assert response.status_code == 404


def test_unknown_player_is_404(client: Client) -> None:
    provider = FakeProvider(profile_error=ProviderError(ProviderErrorCode.PLAYER_NOT_FOUND, "x"))
    response = client(provider).get(BASE)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PLAYER_NOT_FOUND"


def test_cursor_round_trip_rejects_tampering(client: Client) -> None:
    forged = encode_cursor(NOW, 1, None).replace("A", "B", 1) + "!!"
    response = client(_provider()).get(BASE, params={"cursor": forged})
    assert response.status_code == 400
