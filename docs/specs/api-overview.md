# `GET /api/v1/players/{username}/overview`

Status: implemented (Issue 6). Code: `app/analytics/overview.py` (pure metrics),
`app/services/overview.py`, `app/api/v1/routers/players.py`, `app/schemas/overview.py`.

## Behavior

1. The username is normalized (trim, lowercase) and validated; invalid → `400`.
2. The player's dataset is served from cache or refreshed (see `cache-policy.md`).
3. Metrics are computed from stored eligible games in the shared window
   `[now − 30 d, now)` UTC (see `ingestion.md`).

## Response `200`

```json
{
  "username": "example_player",
  "period": { "start": "2026-09-20T12:00:00Z", "end": "2026-10-20T12:00:00Z", "timezone": "UTC" },
  "games_count": 5,
  "wins": 3, "losses": 1, "draws": 1,
  "unknown_results": 0,
  "win_rate": 60.0,
  "current_rating": 1523,
  "current_rating_detail": { "rating": 1523, "as_of": "2026-10-20T12:00:00Z", "source": "provider_stats" },
  "current_streak": { "type": "win", "length": 2 },
  "longest_winning_streak": 2,
  "streak_may_be_incomplete": false,
  "data_status": "fresh",
  "missing_sections": [],
  "refresh_error": null,
  "as_of": "2026-10-20T12:00:00Z",
  "last_successful_update": "2026-10-20T12:00:00Z"
}
```

Values are illustrative.

| Field | Rule |
| ----- | ---- |
| `games_count` | Eligible games, including `unknown_results` |
| `wins` / `losses` / `draws` | Confirmed outcomes from the searched player's perspective |
| `win_rate` | `wins / (wins + losses + draws) * 100`, half-up to 2 decimals; `null` when that denominator is 0 (never `0` for "no games") |
| `current_rating` | Current Rapid rating from the provider's **player stats**, never from a game record; `null` when unavailable (then `missing_sections` contains `current_rating`). `current_rating_detail` adds the provider timestamp and source label |
| `current_streak` | Run of identical outcomes ending with the latest game, ordered by `(played_at, internal game id)`; `null` with no games or when the latest result is unknown |
| `longest_winning_streak` | Longest run of consecutive wins; a loss, draw or unknown result ends a run; `null` with no games, `0` when there are games but no wins |
| `streak_may_be_incomplete` | `true` when unknown results exist or the dataset is partial: streaks may not reflect every game played |
| `data_status` | `fresh`, `partial` (some archives failed; `missing_sections` contains `games`), `stale` (served from last good data; `refresh_error` explains why) |
| `as_of` | When the response was computed; `last_successful_update` is when the data was last refreshed |

Additions to the spec §9.2 example: `unknown_results`, `current_rating_detail`,
`streak_may_be_incomplete`, `refresh_error`. Existing fields keep their meaning.

## Errors (spec §10 envelope)

`{"error": {"code": "...", "message": "...", "request_id": "..."}}`. `request_id` echoes
a safe `X-Request-ID` header or is generated; it is also returned as `X-Request-ID`.

| Status | Code | When |
| ------ | ---- | ---- |
| 400 | `INVALID_USERNAME` | Username fails validation (no upstream request is made) |
| 404 | `PLAYER_NOT_FOUND` | Chess.com confirmed the player does not exist |
| 502 | `UPSTREAM_INVALID_RESPONSE` | Unusable provider data and no cached data |
| 503 | `UPSTREAM_UNAVAILABLE`, `UPSTREAM_RATE_LIMITED`, `REFRESH_IN_PROGRESS`, other | No cached data; `Retry-After` header when known |
| 504 | `UPSTREAM_TIMEOUT` | Provider timeout and no cached data |

Upstream failures with cached data return `200` with `data_status: "stale"`.
