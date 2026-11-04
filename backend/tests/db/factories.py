"""Small builders for database tests. All data is synthetic."""

from __future__ import annotations

import itertools
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Game, GameResult, Player, Provider, TimeClass

_counter = itertools.count(1)

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def make_player(session: Session, username: str | None = None, **fields: object) -> Player:
    player = Player(
        provider=Provider.CHESS_COM,
        username=username or f"player_{next(_counter)}",
        **fields,
    )
    session.add(player)
    session.flush()
    return player


def make_game(
    session: Session,
    white: Player,
    black: Player,
    *,
    provider_game_id: str | None = None,
    played_at: datetime = T0,
    time_class: TimeClass = TimeClass.RAPID,
    result: GameResult = GameResult.WHITE_WIN,
    **fields: object,
) -> Game:
    game = Game(
        provider=Provider.CHESS_COM,
        provider_game_id=provider_game_id or f"live:{next(_counter)}",
        played_at=played_at,
        time_class=time_class,
        result=result,
        white_player_id=white.id,
        black_player_id=black.id,
        **fields,
    )
    session.add(game)
    session.flush()
    return game
