# Game list and game details APIs

Status: implemented (Issue 8). Code: `app/services/games.py`, `app/analytics/pgn.py`,
`app/api/v1/routers/players.py`, `app/schemas/games.py`.

Both endpoints use the player's eligible dataset only (Rapid, standard chess, shared
30-day UTC window; see `ingestion.md`), go through the cache policy, return
`data_status` / `refresh_error` / `as_of` / `last_successful_update`, and use the
error envelope from `api-overview.md`.

## Game identifier

`game_id` in responses and in the details path is the **provider game key**
(`live:<number>` / `daily:<number>`), derived from the Chess.com game URL during
ingestion (`chess-com-provider.md`). It is stable across refreshes and database
rebuilds; internal database ids are never exposed. Limitation: the key depends on
Chess.com keeping the numeric id in game URLs; the URL path format itself may change
(both current and legacy forms are recognized).

## `GET /api/v1/players/{username}/games`

| Query | Rule |
| ----- | ---- |
| `limit` | 1–100, default 20 |
| `result` | optional: `win`, `loss`, `draw`, `unknown` (searched player's perspective) |
| `cursor` | opaque `next_cursor` from the previous page |

- Order: `played_at` descending, then internal game id descending (deterministic for
  equal timestamps).
- Keyset pagination: the cursor holds the last row's `(played_at, id)` and the result
  filter. Pages never overlap or skip rows while the dataset is unchanged. A cursor
  used with a different `result` filter, or tampered with, → `400 INVALID_PARAMETER`.
- `next_cursor: null` means the last page. Responses are always bounded by `limit`.

Item: `game_id`, `played_at`, `result`, `color`, `player_rating`,
`opponent {username, rating}`, `time_control`, `rated`,
`opening {opening_key, name, eco_code}` or `null` (unknown), `game_url`. Ratings are
those reported with the game (`rating_semantics: reported_with_game` in details).

## `GET /api/v1/players/{username}/games/{game_id}`

Returns the game only if it belongs to **this** player's eligible dataset in the
current window. A game of another player, a Blitz game, a game outside the window, or
an unknown id → `404 GAME_NOT_FOUND`.

```json
{
  "username": "example_player",
  "game": { "game_id": "live:1", "...": "same fields as a list item" },
  "rating_semantics": "reported_with_game",
  "pgn": {
    "status": "available",
    "headers": { "Event": "Live Chess", "ECO": "C20" },
    "moves_san": ["e4", "e5", "Nf3", "Nc6"],
    "error": null,
    "raw": "[Event \"Live Chess\"] ..."
  },
  "data_status": "fresh", "refresh_error": null, "as_of": "...", "last_successful_update": "..."
}
```

PGN handling (python-chess 1.11.2, added as a dependency):

| `pgn.status` | Meaning |
| ------------ | ------- |
| `available` | Parsed; `moves_san` is the main line in SAN |
| `missing` | No PGN stored for this game; other fields are still returned |
| `malformed` | Could not be parsed safely; `error` is a code (`illegal_move`, `parse_error`, `no_moves`, `no_game_found`, `too_many_moves`, `pgn_too_large`). Only this game's `pgn` section is affected |

Only a fixed list of PGN headers is exposed; parser messages are never returned.
Parsing is bounded (100 000 characters, 1 000 plies).

## Indexes

The list query filters `player_games` by `player_id` (unique index
`(player_id, game_id)`) and joins `games` by primary key; the 30-day window keeps the
row count small. No new index was added; revisit with `EXPLAIN` on production-sized
data before adding a denormalized `(player_id, played_at)` index.
