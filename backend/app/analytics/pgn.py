"""Bounded PGN parsing with python-chess for game details.

A malformed PGN is a per-game limitation: it yields ``status = "malformed"`` and never
raises, so one bad record cannot affect any other game or endpoint.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from enum import StrEnum

import chess
import chess.pgn

MAX_PGN_CHARS = 100_000  # same bound as ingestion
MAX_PLIES = 1_000
EXPOSED_HEADERS = (
    "Event",
    "Site",
    "Date",
    "Round",
    "White",
    "Black",
    "Result",
    "ECO",
    "ECOUrl",
    "TimeControl",
    "Termination",
    "UTCDate",
    "UTCTime",
    "StartTime",
    "EndDate",
    "EndTime",
    "WhiteElo",
    "BlackElo",
)


class PgnStatus(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    MALFORMED = "malformed"


@dataclass(frozen=True, slots=True)
class PgnDetails:
    status: PgnStatus
    headers: dict[str, str] = field(default_factory=dict)
    moves_san: tuple[str, ...] | None = None
    error: str | None = None  # short machine code, never the parser message


class _CollectingBuilder(chess.pgn.GameBuilder[chess.pgn.Game]):
    """GameBuilder that records errors instead of logging them."""

    def handle_error(self, error: Exception) -> None:
        self.game.errors.append(error)


def parse_pgn(pgn: str | None) -> PgnDetails:
    if pgn is None or not pgn.strip():
        return PgnDetails(PgnStatus.MISSING)
    if len(pgn) > MAX_PGN_CHARS:
        return PgnDetails(PgnStatus.MALFORMED, error="pgn_too_large")
    try:
        game = chess.pgn.read_game(io.StringIO(pgn), Visitor=_CollectingBuilder)
    except Exception:  # defensive: parser bugs must not break the endpoint
        return PgnDetails(PgnStatus.MALFORMED, error="unparseable")
    if game is None:
        return PgnDetails(PgnStatus.MALFORMED, error="no_game_found")

    headers = {k: game.headers[k] for k in EXPOSED_HEADERS if k in game.headers}
    if game.errors:
        code = (
            "illegal_move"
            if any(
                isinstance(e, chess.IllegalMoveError | chess.InvalidMoveError) for e in game.errors
            )
            else "parse_error"
        )
        return PgnDetails(PgnStatus.MALFORMED, headers=headers, error=code)

    board = game.board()
    moves: list[str] = []
    for move in game.mainline_moves():
        if len(moves) >= MAX_PLIES:
            return PgnDetails(PgnStatus.MALFORMED, headers=headers, error="too_many_moves")
        moves.append(board.san(move))
        board.push(move)
    if not moves:
        return PgnDetails(PgnStatus.MALFORMED, headers=headers, error="no_moves")
    return PgnDetails(PgnStatus.AVAILABLE, headers=headers, moves_san=tuple(moves))
