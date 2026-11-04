# Cache Freshness, Refresh, and Stale Fallback

Status: implemented (Issue 5). Code: `app/cache/policy.py`, `app/cache/service.py`,
migration `0002`.

## Provider requirements (verified 2026-10-20)

- PubAPI data refreshes at most every 12 h (one passage of the docs says 24 h).
- Serial requests are unlimited; parallel requests may get `429`.
- `ETag` / `Last-Modified` and `304` are supported (not used yet, see below).

Default TTL is therefore **12 h** (`CACHE_TTL_SECONDS=43200`): refreshing more often
cannot return newer data. The default is a project choice, not a provider guarantee.

## Unit of caching

One `cache_metadata` row per player with `resource_type = player_dataset` and key
`chess_com:player_dataset:<username>`. The data itself lives in the domain tables;
per-month rows (`game_archive_month`) written by ingestion record each archive fetch.

## States

| State | Condition | Behavior | `data_status` |
| ----- | --------- | -------- | ------------- |
| missing | no successful refresh recorded | refresh | — |
| fresh | `now < expires_at` | serve, **no upstream request** | `fresh` (or `partial` if the last refresh was incomplete) |
| expired | `now >= expires_at` | controlled refresh | `fresh` / `partial` after success |
| cooldown | last attempt failed and `now < next_refresh_not_before` | no request; serve last good data | `stale` |
| refreshing | another worker holds the player's refresh lock | no request; serve last good data | `stale` (`refresh_error = REFRESH_IN_PROGRESS`) |
| unavailable | no last good data and refresh failed / skipped | `DatasetUnavailableError(code, retry_after_seconds)` | — |

Freshness is derived from timestamps at read time; the stored `status` only records
the outcome of the last attempt (`refreshing`, `succeeded`, `failed`).

## Rules

- **Failed refresh**: `status = failed`, `last_error_code`, `last_error_at`; the
  previous `last_success_at`, `expires_at`, `record_count` are kept and no game is
  deleted. `next_refresh_not_before = now + max(cooldown, Retry-After)`.
- **Rate limits**: the provider client retries short `Retry-After` waits itself
  (Issue 3); longer ones fail fast and become the cooldown above.
- **Confirmed missing player** (`PLAYER_NOT_FOUND`) is re-raised, never hidden behind
  stale data.
- **Empty but valid**: a successful refresh with no eligible games has
  `record_count = 0` and `data_status = fresh`; a failure is never stored as empty.
- **Partial**: a refresh where some monthly archive failed has `is_complete = false`
  and is served as `partial` until the next complete refresh.
- **Coordination**: a non-blocking PostgreSQL advisory lock
  (`pg_try_advisory_lock(hashtextextended(key, 0))`) on a dedicated connection.
  Works across processes; released automatically if the process dies.
- **Logs**: `dataset refresh` events with `player`, `outcome`
  (`refresh_succeeded`, `refresh_failed`, `skipped_refresh_in_progress`), error code,
  game count and completeness. No payloads.

## Configuration

| Variable | Default | Range |
| -------- | ------- | ----- |
| `CACHE_TTL_SECONDS` | 43200 (12 h) | 60 – 604800 |
| `REFRESH_FAILURE_COOLDOWN_SECONDS` | 300 | 0 – 86400 |

## Not done (follow-ups)

- Conditional requests with `If-None-Match` per monthly archive would save bandwidth;
  validators are already captured in `ResponseMeta`.
- Waiting briefly for an in-progress refresh instead of answering
  `REFRESH_IN_PROGRESS` when there is no cache yet.
