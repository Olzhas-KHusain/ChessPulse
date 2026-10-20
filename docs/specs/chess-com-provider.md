# Chess.com Provider Adapter

Status: implemented (Issue 3). Code: `backend/app/providers/`.
Verified against official documentation on **2026-10-20**:

- Published-Data API: <https://www.chess.com/news/view/published-data-api>
- Support article: <https://support.chess.com/en/articles/9650547-what-is-the-pubapi-and-how-do-i-use-it>

Live responses could **not** be observed from the development environment (the
sandbox cannot call `api.chess.com`). Test fixtures are synthetic and follow the
documented formats. Before release, compare one real response per endpoint with the
fixtures in `backend/tests/providers/fixtures/`.

## Terms and usage constraints

| Topic | Documented guidance | What ChessPulse does |
| ----- | ------------------- | -------------------- |
| Access | Read-only, public data only; no private data | Only the four GET endpoints below |
| Scraping / undocumented endpoints | Not allowed (stated for extensions; we apply it everywhere) | None used; web pages are never fetched |
| Concurrency | Serial access unlimited; parallel requests may get `429`; abnormal activity may be blocked | Synchronous client, one request at a time, bounded retries |
| User-Agent | Recognizable, with contact information | `CHESS_COM_USER_AGENT`; set contact info in production |
| Caching | Data refreshes at most every 12 h (another passage says 24 h); `ETag` / `Last-Modified` and `304` supported | Validators and `max-age` are captured in `ResponseMeta` for the cache layer; conditional requests are not sent yet |
| Compression | Send `Accept-Encoding: gzip` | Sent; the size limit applies to the decompressed body |
| IP and branding | Respect Chess.com IP (board palettes, pieces, glyphs, feature names); do not imply affiliation | Frontend concern; no Chess.com assets are used |
| Data licence | No explicit licence stated | Store only what the MVP needs (see database-schema.md) |

## Endpoints used

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `get_profile` | `/pub/player/{username}` | Public profile, `player_id` |
| `get_stats` | `/pub/player/{username}/stats` | Current Rapid rating (`chess_rapid.last`) |
| `list_archive_months` | `/pub/player/{username}/games/archives` | Available monthly archives |
| `get_month_archive` | `/pub/player/{username}/games/{YYYY}/{MM}` | Completed games ending in that month |

Request paths are always built from a validated username and a validated year/month;
URLs found inside payloads are parsed for information but never requested (no SSRF).
Not used: the PGN download endpoint (PGN is already in each game object) and all
endpoints outside `/pub/player/`.

## HTTP behavior

Timeouts: one `httpx.Timeout(UPSTREAM_TIMEOUT_SECONDS)` applies to connect, read,
write and pool phases of every attempt.

| Upstream outcome | Error code | Retried |
| ---------------- | ---------- | ------- |
| 200 with a JSON object | — | — |
| 200 with invalid JSON, a non-object, or a missing required field | `UPSTREAM_INVALID_RESPONSE` | no |
| 404 / 410 on the profile | `PLAYER_NOT_FOUND` (confirmed missing) | no |
| 404 / 410 on stats or archives | `UPSTREAM_NOT_FOUND` (does **not** prove the player is missing) | no |
| 401 / 403 | `UPSTREAM_FORBIDDEN` | no |
| 429 | `UPSTREAM_RATE_LIMITED` (+ `retry_after`) | yes |
| 500 / 502 / 503 / 504 | `UPSTREAM_UNAVAILABLE` | yes |
| Timeout | `UPSTREAM_TIMEOUT` | yes |
| Connection / network error | `UPSTREAM_UNAVAILABLE` | yes |
| 301/302/307/308 to `https://api.chess.com/pub/...` | followed (max 3 hops) | — |
| Redirect anywhere else, 304, other 3xx | `UPSTREAM_INVALID_RESPONSE` | no |
| Body larger than 25 MiB (decompressed) | `UPSTREAM_INVALID_RESPONSE` | no |
| Any other status | `UPSTREAM_UNKNOWN_ERROR` | no |

Retry policy (`RetryPolicy`):

- At most `UPSTREAM_MAX_RETRIES` extra attempts (default 2), transient failures only.
- Delay: `Retry-After` when present (seconds or HTTP-date), otherwise exponential
  backoff 0.5 s, 1 s, 2 s… with 50–100 % jitter.
- A delay above `UPSTREAM_MAX_RETRY_AFTER_SECONDS` (default 10 s) is never waited: the
  error is raised at once with `retry_after`, so the caller can serve stale data.
- The whole call, including waits, is capped at 60 s.
- Retries are logged with resource, error code, status, attempt and delay only, never
  with response bodies.

## Normalization

All upstream data is untrusted. Required values missing → the record is excluded with
a reason. Optional values missing or malformed → `None` plus an issue code; never a
default.

### Profile

| Field | Source | Rule |
| ----- | ------ | ---- |
| `username` | `username` | Required; trimmed, lowercased, `[a-z0-9_-]{1,64}`; otherwise `UPSTREAM_INVALID_RESPONSE` |
| `provider_player_id` | `player_id` | Positive integer → string; else `None` (+ `player_id_invalid`) |
| `display_name` | `name` | Non-empty text ≤ 255, no control characters |
| `profile_url` | `url` | `https://` on chess.com only |
| `avatar_url` | `avatar` | Any `https://` URL |
| `account_status` | `status` | Raw (e.g. `basic`, `premium`, `closed`, `closed:fair_play_violations`); not interpreted |

### Stats

Only `chess_rapid.last` is used. `rapid_section_present = False` means the player has
no Rapid rating (unknown, not zero). `rating` must be an integer 0–10 000; `date`
(epoch seconds) becomes `rapid_rating_at` and is dropped if the rating is invalid.

### Archive list

`archives` must be a list, otherwise `UPSTREAM_INVALID_RESPONSE`. Each entry must be
`https://api.chess.com/pub/player/{same username}/games/{YYYY}/{MM}`; other entries are
ignored and counted in `archive_urls_ignored:N`. An empty list is a valid result.

`select_archive_months(available, start, end)` picks listed months that overlap
`[start − 1 day, end + 1 day)`: archives are grouped by the month a game ended, but the
time zone of that grouping is not documented. Exact window filtering is done later on
`played_at`.

### Games (monthly archive)

`games` must be a list, otherwise `UPSTREAM_INVALID_RESPONSE`. `{"games": []}` is a
confirmed empty month.

| Value | Source | Rule / exclusion |
| ----- | ------ | ---------------- |
| `provider_game_id` | `url` | `https://(www.)chess.com/game/{live,daily}/<id>` or legacy `/{live,daily}/game/<id>` → `"<namespace>:<id>"`; otherwise **excluded** `missing_game_identifier` |
| `played_at` | `end_time` | Epoch seconds → UTC; missing → `missing_end_time`; before 2000 or more than 1 day after fetch → `invalid_end_time` |
| `time_class` | `time_class` | `rapid`, `blitz`, `bullet`, `daily`; anything else (e.g. `standard` seen in a team-match example) → `unknown_time_class` |
| participants | `white` / `black` `.username` | Required and normalized; missing → `missing_participant`; invalid or same on both sides → `invalid_participant`; archive owner absent → `owner_not_participant` |
| duplicates | — | Same `provider_game_id` twice in one archive → `duplicate_in_archive` (first kept) |
| `rules` | `rules` | Raw variant (`chess`, `chess960`, …) or `None` |
| `rated` | `rated` | Boolean or `None` |
| `time_control` | `time_control` | `^\d+([+/]\d+)?$` (e.g. `600+5`, `1/259200`) or `None` |
| ratings | `white.rating`, `black.rating` | Integer 0–10 000 or `None` |
| `result` | `white.result`, `black.result` | See below |
| `opening` | `eco` URL, else PGN `ECOUrl` | Slug of `https://www.chess.com/openings/<slug>`; name = slug with hyphens as spaces; `eco_code` from PGN `ECO` if `[A-E]\d\d`. No URL → no opening (an ECO code alone is not an exact opening) |
| `pgn` | `pgn` | Kept up to 100 000 characters; larger → `None` + `pgn_too_large`. Only header tags are parsed (regex, bounded); full move parsing is deferred |

Ignored fields: `accuracies` (engine-based, out of MVP scope), `tcn`, `fen`,
`initial_setup`, `uuid`, `start_time`, `tournament`, `match`.

Result codes (documented list):

| Per-side code | Outcome |
| ------------- | ------- |
| `win` | win |
| `agreed`, `repetition`, `stalemate`, `insufficient`, `50move`, `timevsinsufficient` | draw |
| `checkmated`, `timeout`, `resigned`, `lose`, `abandoned`, `kingofthehill`, `threecheck`, `bughousepartnerlose` | loss |
| anything else / missing | unknown (+ `<color>_result_unrecognized`) |

Game result: white win + black loss → `white_win`; the reverse → `black_win`; draw +
draw → `draw`; every other combination → `unknown` (+ `result_codes_inconsistent` when
both codes were known). Unknown results are kept and never counted as losses.

## Limitations and unresolved items

1. **Rating semantics.** The documentation does not say whether `white.rating` /
   `black.rating` is the pre-game or post-game rating. ChessPulse labels it "rating
   reported with the game" and must not present it as either (spec §6.6).
2. **Variants.** Games keep their `rules`. Ingestion must persist only `rules == "chess"`
   for Rapid analytics; `None` (missing) is treated as not verified standard chess.
3. **Username rules** are not published; the accepted pattern is a safe superset.
4. **Renames** are rare per the documentation; a rename is detected by `player_id` when
   the profile is fetched and must be resolved by the ingestion service.
5. **Archive month time zone** is not documented; handled with a one-day margin.
6. **Refresh interval** is documented inconsistently (12 h vs 24 h).
7. **Conditional requests** (`If-None-Match`) are not sent yet; `ResponseMeta` carries
   the validators for the cache issue.
8. **Opening names** are derived from the provider's slug, so punctuation such as the
   hyphen in "Caro-Kann" is shown as a space.
