"""Game list (keyset pagination) and scoped game details."""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.analytics.pgn import parse_pgn
from app.analytics.window import analysis_window
from app.cache.service import PlayerDatasetCache
from app.models import Player, PlayerColor, PlayerResult, Provider
from app.repositories import GameRepository, PageCursor, PlayerGameRow
from app.schemas.games import (
    GameDetailResponse,
    GameListResponse,
    GameSummary,
    OpeningRef,
    OpponentRef,
    PgnOut,
)
from app.schemas.overview import Period
from app.services.breakdowns import InvalidParameterError

MAX_GAMES_LIMIT = 100
DEFAULT_GAMES_LIMIT = 20
_CURSOR_VERSION = 1
_MAX_CURSOR_LENGTH = 256


class GameNotFoundError(LookupError):
    """The game does not exist in the player's eligible dataset."""


def encode_cursor(played_at: datetime, game_id: int, result: PlayerResult | None) -> str:
    payload = {
        "v": _CURSOR_VERSION,
        "t": played_at.isoformat(),
        "i": game_id,
        "r": result.value if result else None,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str, result: PlayerResult | None) -> PageCursor:
    """Validate an opaque cursor; it must have been issued for the same result filter."""
    invalid = InvalidParameterError("cursor", "cursor is invalid or does not match the filters")
    if len(cursor) > _MAX_CURSOR_LENGTH:
        raise invalid
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        data = json.loads(raw)
        played_at = datetime.fromisoformat(data["t"])
        game_id = data["i"]
        ok = (
            data.get("v") == _CURSOR_VERSION
            and isinstance(game_id, int)
            and not isinstance(game_id, bool)
            and played_at.tzinfo is not None
            and data.get("r") == (result.value if result else None)
        )
    except (binascii.Error, ValueError, KeyError, TypeError, AttributeError):
        raise invalid from None
    if not ok:
        raise invalid
    return PageCursor(played_at=played_at, game_id=game_id)


def _summary(row: PlayerGameRow) -> GameSummary:
    game, perspective = row.game, row.perspective
    is_white = perspective.color is PlayerColor.WHITE
    opponent = game.black_player if is_white else game.white_player
    opening = game.opening
    return GameSummary(
        game_id=game.provider_game_id,
        played_at=game.played_at,
        result=perspective.result.value,
        color=perspective.color.value,
        player_rating=game.white_rating if is_white else game.black_rating,
        opponent=OpponentRef(
            username=opponent.username,
            rating=game.black_rating if is_white else game.white_rating,
        ),
        time_control=game.time_control,
        rated=game.rated,
        opening=(
            OpeningRef(
                opening_key=opening.source_opening_id, name=opening.name, eco_code=opening.eco_code
            )
            if opening
            else None
        ),
        game_url=game.game_url,
    )


class GamesService:
    def __init__(self, session: Session, cache: PlayerDatasetCache) -> None:
        self._session = session
        self._cache = cache
        self._games = GameRepository(session)

    def list_games(
        self,
        username: str,
        now: datetime,
        *,
        limit: int = DEFAULT_GAMES_LIMIT,
        cursor: str | None = None,
        result: PlayerResult | None = None,
    ) -> GameListResponse:
        if not 1 <= limit <= MAX_GAMES_LIMIT:
            raise InvalidParameterError("limit", f"limit must be between 1 and {MAX_GAMES_LIMIT}")
        after = decode_cursor(cursor, result) if cursor else None
        status = self._cache.ensure_dataset(username, now)
        window = analysis_window(now)
        rows = self._games.list_player_games(
            status.player_id,
            start=window.start,
            end=window.end,
            limit=limit + 1,  # one extra row tells whether another page exists
            after=after,
            result=result,
        )
        page = list(rows[:limit])
        next_cursor = None
        if len(rows) > limit:
            last = page[-1].game
            next_cursor = encode_cursor(last.played_at, last.id, result)
        player = self._session.get_one(Player, status.player_id)
        return GameListResponse(
            username=player.username,
            period=Period(start=window.start, end=window.end),
            result_filter=result.value if result else None,
            items=[_summary(r) for r in page],
            next_cursor=next_cursor,
            data_status=status.data_status.value,
            refresh_error=status.refresh_error,
            as_of=now,
            last_successful_update=status.last_successful_update,
        )

    def get_game(self, username: str, game_id: str, now: datetime) -> GameDetailResponse:
        if not 1 <= len(game_id) <= 128:
            raise GameNotFoundError(game_id)
        status = self._cache.ensure_dataset(username, now)
        window = analysis_window(now)
        row = self._games.get_player_game(
            status.player_id, Provider.CHESS_COM, game_id, start=window.start, end=window.end
        )
        if row is None:
            raise GameNotFoundError(game_id)
        details = parse_pgn(row.game.pgn)
        player = self._session.get_one(Player, status.player_id)
        return GameDetailResponse(
            username=player.username,
            game=_summary(row),
            pgn=PgnOut(
                status=details.status.value,
                headers=details.headers,
                moves_san=list(details.moves_san) if details.moves_san is not None else None,
                error=details.error,
                raw=row.game.pgn,
            ),
            data_status=status.data_status.value,
            refresh_error=status.refresh_error,
            as_of=now,
            last_successful_update=status.last_successful_update,
        )
