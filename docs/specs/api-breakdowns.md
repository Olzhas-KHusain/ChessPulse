# Rating history, openings and opponents APIs

Status: implemented (Issue 7). Code: `app/analytics/breakdowns.py` (pure),
`app/services/breakdowns.py`, `app/api/v1/routers/players.py`,
`app/schemas/breakdowns.py`.

All three endpoints:

- refresh or reuse the player's dataset through the cache policy (`cache-policy.md`);
- read stored eligible games only (Rapid, standard chess, shared 30-day UTC window,
  see `ingestion.md`) with one query per request;
- use the overview win-rate rule: `wins / (wins + losses + draws) * 100`, 2 decimals,
  `null` when the denominator is 0; `unknown_results` are counted in `games_count`
  but not in the rate;
- return `data_status` (`fresh` / `partial` / `stale`), `refresh_error`, `as_of`,
  `last_successful_update`, `period`;
- use the error envelope and status codes of `api-overview.md`. Invalid query
  parameters → `400 INVALID_PARAMETER` (the message names the parameter, never echoes
  the value).

## `GET /api/v1/players/{username}/rating-history`

Query: `from`, `to` — optional ISO 8601 timestamps **with time zone**. They narrow the
shared window (`[max(from, start), min(to, end))`) and can never widen it; an empty
result range → `400`.

```json
{
  "username": "example_player",
  "period": { "start": "...", "end": "...", "timezone": "UTC" },
  "points": [ { "timestamp": "2026-10-15T12:00:00Z", "rating": 1500, "source": "game_record", "game_id": 17 } ],
  "rating_semantics": "reported_with_game",
  "coverage": "partial",
  "games_considered": 4,
  "games_without_rating": 1,
  "duplicates_removed": 0,
  "data_status": "fresh", "refresh_error": null, "as_of": "...", "last_successful_update": "..."
}
```

- One observation per game that reports the searched player's rating; games without a
  rating produce no point (no interpolation, no daily filling).
- Identical `(timestamp, rating)` observations are reported once (`duplicates_removed`).
- `coverage`: `complete` (every game has a rating and the dataset is complete),
  `partial`, or `none` (no observations).
- `rating_semantics`: the provider does not document whether a game rating is pre- or
  post-game. The current profile rating is not part of this series (see overview).

## `GET /api/v1/players/{username}/openings`

Query: `sort` = `games` (default; sample size desc) | `win_rate` (desc, nulls last,
then sample size) | `name` (asc); `limit` = 1–100, default 20. Ties are broken by name,
then identifier.

Item: `opening_key` (provider opening identifier or `null`), `name`, `eco_code`,
`is_unknown`, `games_count`, `wins`, `losses`, `draws`, `unknown_results`, `win_rate`.
Response also has `sort` and `total_groups` (before `limit`).

Grouping is by the provider opening identifier. Games without one form a single group
named `Unknown` with `opening_key: null` and `is_unknown: true`; no opening or ECO code
is inferred. Sample sizes are always visible; small samples are not marked as
conclusive.

## `GET /api/v1/players/{username}/opponents`

Same `sort` and `limit` as openings (`name` sorts by username).

Item: `opponent_username`, `profile_url`, `last_played_at`, `last_rating` (opponent's
rating reported with the most recent game; `null` if that game had none), and the
outcome fields. `perspective: "searched_player"`: counts are the searched player's
results against that opponent.

Opponents are grouped by their stored player identity (one row per Chess.com account;
usernames are case-insensitive). Similar-looking names (`magnus_fan`, `magnus-fan`)
remain separate groups.
