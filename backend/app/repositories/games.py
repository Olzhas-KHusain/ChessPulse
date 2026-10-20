"""Persistence for ``games`` and ``player_games``."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased, joinedload

from app.analytics.breakdowns import GameRow as BreakdownRow
from app.models import (
    Game,
    GameResult,
    Opening,
    Player,
    PlayerColor,
    PlayerGame,
    PlayerResult,
    Provider,
    TimeClass,
    player_result_for,
)
from app.repositories._batching import chunked

GameKey = tuple[Provider, str]

MAX_PAGE_SIZE = 200

# Optional source fields: a later record that lacks a value keeps the stored one.
_COALESCED_FIELDS = (
    "game_url",
    "time_control",
    "rated",
    "white_rating",
    "black_rating",
    "opening_id",
    "pgn",
)
# Required fields: always taken from the latest validated record.
_REPLACED_FIELDS = ("played_at", "time_class", "white_player_id", "black_player_id", "result")


@dataclass(frozen=True, slots=True)
class GameRecord:
    """One validated, normalized game ready to persist.

    ``provider_game_id`` must be the stable identifier chosen by the provider
    adapter. Optional fields are ``None`` when the source did not supply them.
    """

    provider: Provider
    provider_game_id: str
    played_at: datetime
    time_class: TimeClass
    result: GameResult
    white_player_id: int
    black_player_id: int
    game_url: str | None = None
    time_control: str | None = None
    rated: bool | None = None
    white_rating: int | None = None
    black_rating: int | None = None
    opening_id: int | None = None
    pgn: str | None = None

    @property
    def key(self) -> GameKey:
        return (self.provider, self.provider_game_id)


@dataclass(frozen=True, slots=True)
class PlayerGameRow:
    """A game from a tracked player's perspective, with participants and opening loaded."""

    perspective: PlayerGame
    game: Game


@dataclass(frozen=True, slots=True)
class PageCursor:
    """Keyset position: the ``(played_at, game_id)`` of the last row on the previous page."""

    played_at: datetime
    game_id: int


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")


class GameRepository:
    """Data access for games and player-game associations. Methods never commit."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_games(self, records: Iterable[GameRecord]) -> dict[GameKey, int]:
        """Insert or update games by ``(provider, provider_game_id)``; return their ids.

        Idempotent: repeating the same records creates no rows and changes nothing.
        Within one call, a key that appears twice is stored once (the last record wins).
        Rows are only rewritten, and ``updated_at`` only moves, when a value changes.
        """
        by_key = {record.key: record for record in records}
        if not by_key:
            return {}

        ids: dict[GameKey, int] = {}
        for batch in chunked(list(by_key.values())):
            for record in batch:
                _require_aware(record.played_at, "played_at")
            stmt = insert(Game).values(
                [
                    {
                        "provider": r.provider,
                        "provider_game_id": r.provider_game_id,
                        "played_at": r.played_at,
                        "time_class": r.time_class,
                        "result": r.result,
                        "white_player_id": r.white_player_id,
                        "black_player_id": r.black_player_id,
                        "game_url": r.game_url,
                        "time_control": r.time_control,
                        "rated": r.rated,
                        "white_rating": r.white_rating,
                        "black_rating": r.black_rating,
                        "opening_id": r.opening_id,
                        "pgn": r.pgn,
                    }
                    for r in batch
                ]
            )
            new_values = {
                **{name: stmt.excluded[name] for name in _REPLACED_FIELDS},
                **{
                    name: func.coalesce(stmt.excluded[name], Game.__table__.c[name])
                    for name in _COALESCED_FIELDS
                },
            }
            columns = list(new_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[Game.provider, Game.provider_game_id],
                set_={**new_values, "updated_at": func.now()},
                where=tuple_(*(Game.__table__.c[name] for name in columns)).is_distinct_from(
                    tuple_(*(new_values[name] for name in columns))
                ),
            )
            self._session.execute(stmt)
            rows = self._session.execute(
                select(Game.provider, Game.provider_game_id, Game.id).where(
                    tuple_(Game.provider, Game.provider_game_id).in_([r.key for r in batch])
                )
            )
            ids.update({(provider, gid): game_id for provider, gid, game_id in rows})
        return ids

    def link_player_games(
        self, player_id: int, links: Iterable[tuple[int, PlayerColor, GameResult]]
    ) -> None:
        """Associate games with a tracked player, idempotently.

        Each link is ``(game_id, color, game_result)``; the player's own result is
        derived with :func:`app.models.player_result_for`, the same rule the database
        verifies at commit.
        """
        by_game: dict[int, tuple[PlayerColor, PlayerResult]] = {
            game_id: (color, player_result_for(color, result)) for game_id, color, result in links
        }
        if not by_game:
            return
        items = sorted(by_game.items())
        for batch in chunked(items):
            stmt = insert(PlayerGame).values(
                [
                    {"player_id": player_id, "game_id": game_id, "color": color, "result": res}
                    for game_id, (color, res) in batch
                ]
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[PlayerGame.player_id, PlayerGame.game_id],
                set_={
                    "color": stmt.excluded.color,
                    "result": stmt.excluded.result,
                    "updated_at": func.now(),
                },
                where=tuple_(PlayerGame.color, PlayerGame.result).is_distinct_from(
                    tuple_(stmt.excluded.color, stmt.excluded.result)
                ),
            )
            self._session.execute(stmt)

    def list_player_games(
        self,
        player_id: int,
        *,
        start: datetime,
        end: datetime,
        time_class: TimeClass = TimeClass.RAPID,
        limit: int = 50,
        after: PageCursor | None = None,
        result: PlayerResult | None = None,
    ) -> Sequence[PlayerGameRow]:
        """Return a tracked player's games in ``[start, end)``, newest first.

        * The window is start-inclusive and end-exclusive (spec §6.1).
        * Ties on ``played_at`` are broken by ``games.id`` descending, so the order
          and keyset pagination are deterministic.
        * Participants and opening are loaded in the same query (no N+1).
        """
        _require_aware(start, "start")
        _require_aware(end, "end")
        if start >= end:
            raise ValueError("start must be earlier than end")
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")

        stmt = (
            select(PlayerGame, Game)
            .join(Game, Game.id == PlayerGame.game_id)
            .where(
                PlayerGame.player_id == player_id,
                Game.time_class == time_class,
                Game.played_at >= start,
                Game.played_at < end,
            )
            .options(
                joinedload(Game.white_player),
                joinedload(Game.black_player),
                joinedload(Game.opening),
            )
            .order_by(Game.played_at.desc(), Game.id.desc())
            .limit(limit)
        )
        if after is not None:
            _require_aware(after.played_at, "after.played_at")
            stmt = stmt.where(
                tuple_(Game.played_at, Game.id) < tuple_(after.played_at, after.game_id)
            )
        if result is not None:
            stmt = stmt.where(PlayerGame.result == result)
        return [
            PlayerGameRow(perspective=perspective, game=game)
            for perspective, game in self._session.execute(stmt)
        ]

    def list_outcomes(
        self,
        player_id: int,
        *,
        start: datetime,
        end: datetime,
        time_class: TimeClass = TimeClass.RAPID,
    ) -> list[tuple[datetime, int, PlayerResult]]:
        """``(played_at, game_id, result)`` for every game of a tracked player in
        ``[start, end)``. A single lightweight query; the window bounds the row count."""
        _require_aware(start, "start")
        _require_aware(end, "end")
        stmt = (
            select(Game.played_at, Game.id, PlayerGame.result)
            .join(PlayerGame, PlayerGame.game_id == Game.id)
            .where(
                PlayerGame.player_id == player_id,
                Game.time_class == time_class,
                Game.played_at >= start,
                Game.played_at < end,
            )
            .order_by(Game.played_at, Game.id)
        )
        return [(played_at, gid, result) for played_at, gid, result in self._session.execute(stmt)]

    def list_breakdown_rows(
        self, player_id: int, *, start: datetime, end: datetime
    ) -> list[BreakdownRow]:
        """Every Rapid game of a tracked player in ``[start, end)`` with the opponent and
        opening columns needed by breakdowns, in one query (no N+1)."""
        _require_aware(start, "start")
        _require_aware(end, "end")
        white, black = aliased(Player), aliased(Player)
        stmt = (
            select(
                Game.id.label("gid"),
                Game.played_at.label("played_at"),
                PlayerGame.color.label("color"),
                PlayerGame.result.label("result"),
                Game.white_rating.label("w_rating"),
                Game.black_rating.label("b_rating"),
                white.id.label("w_id"),
                white.username.label("w_name"),
                black.id.label("b_id"),
                black.username.label("b_name"),
                Opening.source_opening_id.label("o_key"),
                Opening.name.label("o_name"),
                Opening.eco_code.label("eco"),
            )
            .join(PlayerGame, PlayerGame.game_id == Game.id)
            .join(white, white.id == Game.white_player_id)
            .join(black, black.id == Game.black_player_id)
            .outerjoin(Opening, Opening.id == Game.opening_id)
            .where(
                PlayerGame.player_id == player_id,
                Game.time_class == TimeClass.RAPID,
                Game.played_at >= start,
                Game.played_at < end,
            )
            .order_by(Game.played_at, Game.id)
        )
        rows: list[BreakdownRow] = []
        for r in self._session.execute(stmt).mappings():
            is_white = r["color"] is PlayerColor.WHITE
            rows.append(
                BreakdownRow(
                    game_id=r["gid"],
                    played_at=r["played_at"],
                    color=r["color"],
                    result=r["result"],
                    player_rating=r["w_rating"] if is_white else r["b_rating"],
                    opponent_id=r["b_id"] if is_white else r["w_id"],
                    opponent_username=r["b_name"] if is_white else r["w_name"],
                    opponent_rating=r["b_rating"] if is_white else r["w_rating"],
                    opening_key=r["o_key"],
                    opening_name=r["o_name"],
                    eco_code=r["eco"],
                )
            )
        return rows

    def get_player_game(
        self,
        player_id: int,
        provider: Provider,
        provider_game_id: str,
        *,
        start: datetime,
        end: datetime,
    ) -> PlayerGameRow | None:
        """One game, only if it belongs to the player's eligible Rapid dataset in
        ``[start, end)``; otherwise ``None`` (other players' or ineligible games)."""
        _require_aware(start, "start")
        _require_aware(end, "end")
        stmt = (
            select(PlayerGame, Game)
            .join(Game, Game.id == PlayerGame.game_id)
            .where(
                PlayerGame.player_id == player_id,
                Game.provider == provider,
                Game.provider_game_id == provider_game_id,
                Game.time_class == TimeClass.RAPID,
                Game.played_at >= start,
                Game.played_at < end,
            )
            .options(
                joinedload(Game.white_player),
                joinedload(Game.black_player),
                joinedload(Game.opening),
            )
        )
        row = self._session.execute(stmt).first()
        return PlayerGameRow(perspective=row[0], game=row[1]) if row else None
