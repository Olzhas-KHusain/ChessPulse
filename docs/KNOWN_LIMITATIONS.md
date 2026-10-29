# Known limitations and deferred work

## Data and provider

- **Freshness.** A player's dataset is cached for 12 h (`CACHE_TTL_SECONDS`); Chess.com
  documents that its public data refreshes at most every 12 h (another passage says
  24 h). Games finished after the last refresh appear only after the next one. Every
  response carries `last_successful_update` and `data_status`.
- **Rating semantics.** Game records do not document whether a rating is pre- or
  post-game; ChessPulse labels it "reported with the game". The current rating comes
  from the player's stats and is shown separately.
- **Variants.** Only `rules == "chess"` Rapid games are analysed; Chess960 and other
  variants, and games without a `rules` value, are excluded.
- **Unknown results** are kept as `unknown`, excluded from the win rate, and they break
  streaks (`streak_may_be_incomplete`).
- **Openings** are identified by Chess.com's opening page slug. The display name is the
  slug with a documented orthography table that restores apostrophes and hyphens
  ("King's Pawn", "Caro-Kann", "Smith-Morra"); a name whose slug is not in the table is
  shown with spaces where the standard spelling may need a hyphen. No external opening
  database is used, and the provider's `Undefined` placeholder is treated as unknown.
- **Renames.** Detected via `player_id` when the profile is fetched. Renaming into a
  username already stored for another account (e.g. an opponent row) fails the refresh
  (HTTP 500); expected to be extremely rare.
- **Archive month time zone** is undocumented; neighbouring months are fetched with a
  one-day margin.
- **Live contract not observed** from the build environment; fixtures are synthetic.

## Behaviour

- **First load contention.** If a player has no cache yet and a refresh is already
  running in another worker, other requests get `503 REFRESH_IN_PROGRESS` instead of
  waiting. The UI avoids this by loading the overview first.
- **Long refreshes.** A cold refresh makes up to 5 serial upstream requests; with
  retries and Retry-After waits it can hold a worker thread for tens of seconds.
- **No application-level rate limiting** (spec §10 lists 429 as optional). Upstream load
  is bounded by caching, cooldowns and serial access only.
- **Data retention.** Stored games are never deleted; a cleanup policy for games older
  than the window is not implemented.
- **PGN** is stored permanently when supplied (open decision, spec §20).
- **Conditional requests** (`If-None-Match`) are not sent; validators are captured.

## Explicitly deferred (not in the MVP)

- Engine analysis: accuracy, Brilliant moves, blunders, centipawn loss, estimated Elo
  (spec §6.10). The adapter ignores the provider's `accuracies` field; no such value is
  shown anywhere.
- `player_statistics` aggregate table (not needed; aggregates are computed per request).
- Blitz, Bullet, Daily and variant analytics; windows other than 30 days.
- Accounts, authentication, private Chess.com data.
- Deployment target, containers for backend/frontend, production monitoring.
