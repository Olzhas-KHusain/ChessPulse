"""Unit tests for individual normalization rules."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.models import GameResult, PlayerResult
from app.providers.chess_com.normalize import (
    DRAW_CODES,
    LOSS_CODES,
    MAX_PGN_CHARS,
    epoch_to_utc,
    game_result,
    normalize_game,
    parse_game_id,
    parse_opening_url,
    parse_pgn_headers,
    side_outcome,
)
from app.providers.types import ExcludedGame, ExclusionReason, ProviderGame

LATEST = datetime(2026, 10, 21, tzinfo=UTC)


def _game(**overrides: Any) -> dict[str, Any]:
    game: dict[str, Any] = {
        "url": "https://www.chess.com/game/live/42",
        "end_time": 1790000000,
        "time_class": "rapid",
        "rules": "chess",
        "white": {"username": "me", "rating": 1500, "result": "win"},
        "black": {"username": "you", "rating": 1490, "result": "resigned"},
    }
    game.update(overrides)
    return game


def _normalized(**overrides: Any) -> ProviderGame:
    result = normalize_game(_game(**overrides), owner="me", latest_allowed=LATEST)
    assert isinstance(result, ProviderGame), result
    return result


def _excluded(**overrides: Any) -> ExclusionReason:
    result = normalize_game(_game(**overrides), owner="me", latest_allowed=LATEST)
    assert isinstance(result, ExcludedGame), result
    return result.reason


@pytest.mark.parametrize("code", sorted(DRAW_CODES))
def test_every_documented_draw_code(code: str) -> None:
    assert side_outcome(code) is PlayerResult.DRAW


@pytest.mark.parametrize("code", sorted(LOSS_CODES))
def test_every_documented_loss_code(code: str) -> None:
    assert side_outcome(code) is PlayerResult.LOSS


@pytest.mark.parametrize("code", [None, "", "mystery", "WIN"])
def test_unknown_codes_are_unknown_not_loss(code: str | None) -> None:
    assert side_outcome(code) is PlayerResult.UNKNOWN


@pytest.mark.parametrize(
    ("white", "black", "expected"),
    [
        (PlayerResult.WIN, PlayerResult.LOSS, GameResult.WHITE_WIN),
        (PlayerResult.LOSS, PlayerResult.WIN, GameResult.BLACK_WIN),
        (PlayerResult.DRAW, PlayerResult.DRAW, GameResult.DRAW),
        (PlayerResult.WIN, PlayerResult.WIN, GameResult.UNKNOWN),
        (PlayerResult.WIN, PlayerResult.DRAW, GameResult.UNKNOWN),
        (PlayerResult.UNKNOWN, PlayerResult.LOSS, GameResult.UNKNOWN),
    ],
)
def test_game_result_combination(
    white: PlayerResult, black: PlayerResult, expected: GameResult
) -> None:
    assert game_result(white, black) is expected


def test_inconsistent_codes_are_flagged() -> None:
    game = _normalized(black={"username": "you", "result": "win"})
    assert game.result is GameResult.UNKNOWN
    assert "result_codes_inconsistent" in game.issues


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.chess.com/game/live/123", "live:123"),
        ("https://www.chess.com/game/live/123/", "live:123"),
        ("https://chess.com/game/daily/9", "daily:9"),
        ("https://www.chess.com/live/game/123", "live:123"),
        ("https://www.chess.com/daily/game/7", "daily:7"),
        ("https://www.chess.com/game/live/00123", "live:123"),
        ("http://www.chess.com/game/live/123", None),
        ("https://evil.example/game/live/123", None),
        ("https://www.chess.com/game/live/abc", None),
        ("https://www.chess.com/game/123", None),
        (123, None),
        (None, None),
    ],
)
def test_parse_game_id(url: object, expected: str | None) -> None:
    assert parse_game_id(url) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://www.chess.com/openings/Sicilian-Defense-Open-2...Nc6",
            ("Sicilian-Defense-Open-2...Nc6", "Sicilian Defense Open 2...Nc6"),
        ),
        ("https://www.chess.com/openings/Kings-Gambit/", ("Kings-Gambit", "King's Gambit")),
        (
            "https://www.chess.com/openings/Caro-Kann-Defense-2.Nc3-d5",
            ("Caro-Kann-Defense-2.Nc3-d5", "Caro-Kann Defense 2.Nc3 d5"),
        ),
        (
            "https://www.chess.com/openings/Queens-Pawn-Opening-Mikenas-Defense",
            ("Queens-Pawn-Opening-Mikenas-Defense", "Queen's Pawn Opening Mikenas Defense"),
        ),
        (
            "https://www.chess.com/openings/Sicilian-Defense-Smith-Morra-Gambit-2...cxd4",
            (
                "Sicilian-Defense-Smith-Morra-Gambit-2...cxd4",
                "Sicilian Defense Smith-Morra Gambit 2...cxd4",
            ),
        ),
        (
            "https://www.chess.com/openings/Giuoco-Piano-Game-Giuoco-Pianissimo-5...O-O",
            (
                "Giuoco-Piano-Game-Giuoco-Pianissimo-5...O-O",
                "Giuoco Piano Game Giuoco Pianissimo 5...O-O",
            ),
        ),
        (
            "https://www.chess.com/openings/Vienna-Game-3...O-O-O",
            ("Vienna-Game-3...O-O-O", "Vienna Game 3...O-O-O"),
        ),
        # Chess.com's placeholder page is not an opening.
        ("https://www.chess.com/openings/Undefined", None),
        ("https://www.chess.com/openings/undefined", None),
        ("https://www.chess.com/openings/", None),
        ("https://www.chess.com/openings/<script>", None),
        ("https://www.chess.com/member/x", None),
        ("https://evil.example/openings/Fake", None),
    ],
)
def test_parse_opening_url(url: str, expected: tuple[str, str] | None) -> None:
    assert parse_opening_url(url) == expected


def test_parse_pgn_headers_stops_at_movetext() -> None:
    pgn = '[Event "Live"]\n[ECO "C20"]\n[Note "has \\"quotes\\""]\n\n1. e4 e5\n[Fake "x"]\n'
    assert parse_pgn_headers(pgn) == {"Event": "Live", "ECO": "C20", "Note": 'has "quotes"'}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1790000000, datetime(2026, 9, 21, 14, 13, 20, tzinfo=UTC)),
        (1790000000.0, datetime(2026, 9, 21, 14, 13, 20, tzinfo=UTC)),
        (0, None),
        (-1, None),
        (True, None),
        ("1790000000", None),
        (1.5, None),
        (float("nan"), None),
        (10**20, None),
    ],
)
def test_epoch_to_utc(value: object, expected: datetime | None) -> None:
    assert epoch_to_utc(value) == expected


def test_same_player_on_both_sides_is_excluded() -> None:
    assert (
        _excluded(black={"username": "ME", "result": "resigned"})
        is ExclusionReason.INVALID_PARTICIPANT
    )


def test_oversized_pgn_is_dropped_but_game_kept() -> None:
    game = _normalized(pgn="x" * (MAX_PGN_CHARS + 1))
    assert game.pgn is None
    assert game.issues == ("pgn_too_large",)


def test_opening_falls_back_to_pgn_ecourl_and_validates_eco() -> None:
    pgn = '[ECO "Z99"]\n[ECOUrl "https://www.chess.com/openings/French-Defense"]\n\n1. e4 e6\n'
    game = _normalized(pgn=pgn)
    assert game.opening is not None
    assert game.opening.source_opening_id == "French-Defense"
    assert game.opening.eco_code is None
    assert game.issues == ("eco_code_invalid",)


def test_eco_code_alone_does_not_invent_an_opening() -> None:
    game = _normalized(pgn='[ECO "B20"]\n\n1. e4 c5\n')
    assert game.opening is None


@pytest.mark.parametrize("rating", [-1, 10_001, 1500.5, True, "1500"])
def test_implausible_ratings_are_dropped(rating: object) -> None:
    game = _normalized(white={"username": "me", "rating": rating, "result": "win"})
    assert game.white.rating is None
    assert "white_rating_invalid" in game.issues


def test_participant_usernames_are_normalized() -> None:
    game = _normalized(black={"username": "  You ", "result": "resigned"})
    assert game.black.username == "you"
