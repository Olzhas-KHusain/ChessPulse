# Game Ingestion and Eligibility

Status: implemented (Issue 4). Code: `app/analytics/window.py`,
`app/services/eligibility.py`, `app/services/ingestion.py`.

## Analysis window (single shared definition)

`analysis_window(now)` → `[now − 30 days, now)` in UTC: start **inclusive**, end
**exclusive**. Naive datetimes are rejected. All filtering and, later, all API
responses must use this function.

## Eligibility rule

A normalized provider game enters the analytics dataset only if:

| # | Rule | Exclusion reason |
|---|------|------------------|
| 1 | `time_class == "rapid"` (provider classification; `time_control` text is never used to infer it) | `not_rapid` |
| 2 | `rules` present … | `rules_unverified` |
| 3 | … and equal to `chess` (variants have separate ratings) | `non_standard_variant` |
| 4 | `played_at` (game end time) inside the window | `outside_window` |

Completion: PubAPI monthly archives contain finished games only, so archived games
are complete. A game whose result cannot be classified is kept with result
`unknown`; it is never counted as a loss.

Records the provider could not normalize are excluded earlier with the reasons listed
in `chess-com-provider.md` (missing identifier, missing end time, unknown time class,
missing participant, …). A game present in two monthly archives is stored once
(`duplicate_across_archives`).

## Ingestion flow

`GameIngestionService(session, provider).ingest_player(username, now)`:

1. Profile. A confirmed missing player or an outage raises `ProviderError`; nothing is
   written. A profile whose stable `player_id` belongs to a stored player with another
   username is treated as a confirmed rename: the stored row is renamed.
2. Stats. Failure is tolerated (`report.stats_error`); the previous rating is kept.
3. Archive list → months overlapping the window (one-day margin).
4. Each month is fetched independently. A failed month is recorded in
   `report.months_failed` and in `cache_metadata` as `failed`, keeping the previous
   `last_success_at`; other months continue.
5. Eligible games, participants, openings and the searched player's associations are
   upserted in one transaction (idempotent; repeated runs do not add rows).
6. Successful months are recorded in `cache_metadata` with `record_count`
   (0 = confirmed empty month).

`IngestionReport` exposes `eligible_games`, `excluded` (counts by reason),
`months_failed`, and `complete` (false when any month failed). Exclusion counts are
also logged; individual excluded payloads are not stored.

## Decisions

- Games outside the window or not eligible are **not persisted**.
- Persisted games are never deleted by a failed or partial refresh.
- TTL / freshness decisions (`expires_at`) are left to the cache issue; ingestion only
  records what happened.
