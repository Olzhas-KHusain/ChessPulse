# Cross-game form report API

Status: implemented. Code: `app/analytics/form.py` (pure aggregation),
`app/services/form.py`, `app/repositories/analysis.py`, `app/schemas/form.py`,
`app/api/v1/routers/players.py`.

The report answers one question: **where does this player's win probability actually
leak?** It aggregates every stored engine analysis in the current scope instead of
reviewing one game. It is the product's main differentiator: the numbers cannot be
produced from a single game or from the provider's own accuracy field.

## Scope

Both endpoints use the player's eligible dataset (Rapid, standard chess, current 30-day
UTC window; see `ingestion.md` and `api-games.md`) and the cache policy. The scope is
parameterised by `time_class` internally, but the public API currently exposes only
`rapid`; broader time classes and arbitrary date ranges are the next scaling step.

## `POST /api/v1/players/{username}/form/analyze`

Queues every game in the scope that has no completed analysis for the current engine
profile. A failed job is reset to `queued`; an active job keeps its progress. Idempotent.

```json
{
  "username": "example_player",
  "time_class": "rapid",
  "games_total": 43,
  "already_analyzed": 1,
  "queued": 42,
  "pending": 42
}
```

`pending` counts jobs that are `queued` or `running` in this scope after the request.

## `GET /api/v1/players/{username}/form`

```json
{
  "username": "example_player",
  "period": { "start": "2026-09-29T10:24:48Z", "end": "2026-10-29T10:24:48Z", "timezone": "UTC" },
  "time_class": "rapid",
  "data_status": "fresh",
  "refresh_error": null,
  "as_of": "2026-10-29T10:24:48Z",
  "last_successful_update": "2026-10-29T08:32:00Z",
  "games_total": 43,
  "games_analyzed": 42,
  "games_queued": 0,
  "games_running": 0,
  "games_failed": 1,
  "accuracy_mean": 78.4,
  "opponent_accuracy_mean": 79.1,
  "acpl_mean": 91.7,
  "wp_loss_per_game": 121.5,
  "accuracy_trend": [
    {
      "game_id": "live:1",
      "played_at": "2026-10-01T10:00:00Z",
      "color": "white",
      "result": "win",
      "opponent": "rival",
      "accuracy": 84.2,
      "acpl": 52.1,
      "blunders": 0,
      "mistakes": 2
    }
  ],
  "by_phase": [
    {
      "key": "opening",
      "label": "Opening (moves 1–10)",
      "games": 42,
      "moves": 420,
      "blunders": 6,
      "mistakes": 19,
      "inaccuracies": 31,
      "acpl": 48.3,
      "accuracy": 86.1,
      "wp_loss_per_game": 9.4
    }
  ],
  "by_color": [],
  "by_opening": [],
  "top_moments": [
    {
      "game_id": "live:1",
      "played_at": "2026-10-01T10:00:00Z",
      "color": "white",
      "opponent": "rival",
      "move_number": 18,
      "san": "Qh5",
      "classification": "blunder",
      "cp_loss": 640,
      "wp_loss": 42.5,
      "phase": "middlegame",
      "opening_name": "Caro-Kann Defense",
      "game_url": "https://www.chess.com/game/live/1"
    }
  ],
  "primary_leak": {
    "kind": "opening",
    "label": "Caro-Kann Defense",
    "wp_loss_per_game": 26.4,
    "games": 3,
    "moves": 30,
    "blunders": 3,
    "mistakes": 4
  }
}
```

`accuracy_trend` is ordered oldest first. `primary_leak` is `null` when no group reaches
the minimum sample size or when the largest loss is zero.

## Metric definitions

All values are derived from stored engine payloads; nothing is inferred from results.

| Metric | Definition |
| ------ | ---------- |
| `wp_loss_per_game` | Sum over the player's own moves of the drop in the engine's win probability (percentage points), divided by the number of analysed games. Can exceed 100 for long, swingy games. |
| `accuracy` (group) | Mean per-move accuracy inside the group, using the documented Lichess formula (see `api-analysis.md`). |
| `acpl` (group) | Mean centipawn loss of the player's moves inside the group. |
| `accuracy_mean` | Mean of the per-game accuracies, one vote per game. |
| `blunders` / `mistakes` / `inaccuracies` | Counts of the player's own moves with that label. |

## Grouping rules

- **Phases by move number**, stated honestly in the label: opening 1–10, middlegame
  11–30, late 31+. This is not material-based endgame detection.
- **Colour**: White / Black.
- **Openings**: grouped by Chess.com opening slug; openings with fewer than two analysed
  games are omitted from the table.
- A group can become the **primary leak** only with **at least three analysed games**.
  Ties rank openings first, then phases, then colours; within the same kind, more
  blunders + mistakes wins, then more moves.
- `top_moments` contains at most 10 of the player's inaccuracies, mistakes and blunders,
  sorted by win-probability loss.

## Partial coverage

`games_analyzed < games_total` is normal while the worker is still running. The UI shows
"N of M eligible games analysed" and polls while `games_queued + games_running > 0`.
Games that failed keep their `failed` state and are excluded from the aggregates;
`games_failed` reports how many.

## Error codes

Same envelope and codes as `api-overview.md`: `404 PLAYER_NOT_FOUND` for an unknown
player, `503 REFRESH_IN_PROGRESS` during a cold refresh, and the provider error codes
when neither fresh nor cached data exists.
