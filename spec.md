# ChessPulse — Product and Technical Specification

**Status:** Draft for implementation  
**Product:** ChessPulse  
**Architecture:** Modular monolith  
**API prefix:** `/api/v1`

## 1. Product Summary

ChessPulse is a web application that provides accessible performance analytics for a Chess.com player's recent Rapid games.

A visitor enters a Chess.com username and receives a dashboard based on eligible games from the most recent rolling 30-day period.

The application aims to make recent performance easier to understand than a raw list of game results.

## 2. Problem Statement

Players can access individual games and basic profile information, but interpreting recent performance across games requires manual review.

ChessPulse consolidates supported data into:
- Win, loss, and draw counts
- Win rate
- Winning streak information
- Available rating observations
- Opening statistics
- Opponent statistics
- Recent game history

The product must distinguish trustworthy calculated results from missing or incomplete source data.

## 3. Goals

1. Make recent Rapid performance accessible through a single dashboard.
2. Require no account creation.
3. Calculate all MVP metrics deterministically from validated source data.
4. Reuse cached data to reduce redundant provider requests.
5. Recover gracefully from partial provider failures.
6. Keep the implementation understandable and testable.
7. Establish an architecture that can support future engine analysis without implementing it in the MVP.

## 4. Non-Goals

The MVP does not include:
- Chess.com login or private account access
- Playing chess inside ChessPulse
- A social network, comments, or messaging
- Paid subscriptions
- A custom chess engine
- Engine-based accuracy, centipawn loss, Brilliant moves, or blunder detection
- Engine-estimated Elo
- Guaranteed complete rating history for every day
- Guaranteed access to all historical games regardless of provider availability
- Analysis of Blitz, Bullet, Daily, or other modes
- A claim that ChessPulse ratings replace the official Chess.com rating

## 5. Target User and Primary Journey

### Target user

A Chess.com player who wants to understand their recent Rapid performance without manually inspecting every game.

### Primary journey

1. Open ChessPulse.
2. Enter a Chess.com username.
3. Submit the search.
4. See validation feedback if the username is invalid.
5. View a loading state while data is fetched or refreshed.
6. Receive an overview of eligible Rapid games from the last 30 days.
7. Explore rating observations, openings, opponents, and games.
8. Open an individual game for its available details.
9. Understand whether the displayed data is fresh, cached, stale, or incomplete.

No authentication is required for this flow.

## 6. Scope and Metric Rules

### 6.1 Analysis window

Use a rolling 30-day window based on UTC timestamps.

Proposed boundary convention:
- Start: `now_utc - 30 days`, inclusive.
- End: `now_utc`, exclusive.

Only completed games whose authoritative game timestamp falls within this interval are eligible.

Use one shared window definition across the API, analytics, and UI. A cached response must communicate the data's relevant as-of or refresh time.

### 6.2 Game mode

Only Rapid games are eligible.

Use the provider's documented time-control classification where available. Do not infer Rapid solely from a display label or arbitrary estimated duration.

If a game cannot be classified reliably, exclude it from Rapid-only calculations and record the exclusion reason internally.

### 6.3 Game outcomes

Normalize eligible games into:
- `win`
- `loss`
- `draw`
- `unknown`

Only confirmed completed wins, losses, and draws contribute to the outcome counts.

Unknown or unfinished outcomes must not silently count as losses.

### 6.4 Overview metrics

Required fields:
- `games_count`
- `wins`
- `losses`
- `draws`
- `win_rate`
- `current_rating`, when available
- `current_streak`, when determinable
- `longest_winning_streak`, when determinable
- `data_status`
- `as_of`
- `last_successful_update`

Formula:

`win_rate = wins / (wins + losses + draws) * 100`

If the denominator is zero, `win_rate` is `null`.

Return a consistent numeric precision in the API. The frontend may format the value for display, but must not recalculate it using different rules.

The product must document whether win rate counts draws in the denominator. This specification includes draws in the denominator.

### 6.5 Streaks

Process eligible games chronologically, using a deterministic tie-breaker when timestamps are equal.

- A win extends the winning streak.
- A loss or draw ends the winning streak.
- The current streak describes the latest eligible completed game sequence.
- If no eligible games exist, the streak is unavailable rather than a fabricated zero-length streak.
- If source data is incomplete, indicate that the streak may not represent every game played in the period.

Define response fields so a client can distinguish streak type from streak length.

### 6.6 Rating observations

The application may display rating observations obtained from trustworthy game records or profile data.

Do not claim that these observations form a complete daily rating history unless the source guarantees that completeness.

Requirements:
- Preserve the timestamp and source of each observation.
- Do not fabricate missing daily points.
- Do not interpolate values by default.
- Distinguish current profile rating from the player's rating associated with a particular game.
- Document whether a value represents rating before or after a game.
- Use Rapid-specific rating data only.

If rating history cannot be reconstructed reliably, return an empty or partial series with an explanatory status.

### 6.7 Opening statistics

Group games by a reliably identified opening.

Possible sources include validated PGN metadata and a maintained opening-name mapping that is permitted for use.

Rules:
- Normalize equivalent names and known identifiers where possible.
- Do not infer an exact opening from insufficient data.
- Group unresolved games under an explicit `Unknown` category or a documented missing category.
- Report sample size for each opening.
- Calculate outcomes using the same definitions as the overview.
- Avoid ranking tiny samples as conclusive evidence of player strength.

Opening win rate uses the same denominator convention, including draws.

### 6.8 Opponent statistics

Normalize opponents using a stable provider identifier, such as a documented username or profile identifier.

Do not merge opponents solely because their display names look similar.

For each opponent, expose available:
- Identifier and display name
- Number of eligible games
- Wins, losses, draws
- Win rate
- Relevant rating observations, when available

Be explicit about perspective: outcome counts refer to the ChessPulse player, not the opponent.

### 6.9 Individual games

Where available, display:
- Provider game identifier
- Played-at timestamp
- Player and opponent
- Outcome from the searched player's perspective
- Time control
- Ratings associated with the game
- Opening metadata
- Game URL
- PGN or parsed game details where permitted and available

A malformed individual PGN must not cause the entire player analysis to fail.

### 6.10 Deferred engine metrics

Engine-based metrics are out of MVP scope.

A later engine-analysis stage may evaluate Stockfish integration, computational cost, reproducibility, and licensing/distribution obligations.

Until then, never label a heuristic or unverified estimate as engine accuracy, Brilliant moves, blunders, or estimated Elo.

## 7. System Architecture

### 7.1 Architecture style

Use a modular monolith with one backend application and one frontend application.

Do not introduce microservices, message brokers, or a separate distributed cache unless measured requirements justify them.

### 7.2 Backend modules

**API layer**
- FastAPI routers
- Path/query validation
- HTTP status mapping
- Response schemas

**Service layer**
- Player lookup orchestration
- Game retrieval
- Analytics calculations
- Cache policy coordination
- Partial-data aggregation

**Provider layer**
- Chess.com HTTP client
- Upstream response validation
- Provider-specific data normalization
- Timeouts and rate-limit handling

**Repository layer**
- Database queries and persistence
- Transaction management
- Upsert and deduplication logic

**Analytics layer**
- Outcome calculations
- Streaks
- Rating observations
- Opening grouping
- Opponent grouping

**Cache layer**
- Freshness metadata
- Expiration
- Last-known-good data
- Refresh coordination

### 7.3 Frontend modules

- Username search
- Player overview
- Rating history
- Opening statistics
- Opponent statistics
- Game list and filters
- Game details
- Shared loading, error, stale, and partial-data components

Use a dedicated API client and typed response models.

### 7.4 Technology stack

- Frontend: React, TypeScript, Vite, Tailwind CSS, Recharts
- Backend: Python, FastAPI, Pydantic v2
- Database: PostgreSQL
- ORM/migrations: SQLAlchemy 2.x and Alembic
- HTTP client: HTTPX
- Chess data parsing: python-chess
- Backend tests: pytest
- Frontend tests: Vitest and React Testing Library
- Local development: Docker Compose

Pin dependencies in project configuration. Confirm supported runtime versions and library APIs during implementation.

## 8. External Provider Integration

Use documented public Chess.com interfaces where available.

Before implementation, verify:
- Player lookup behavior
- Archive discovery and retrieval
- Availability of Rapid game records
- Available PGN and rating fields
- Pagination or archive structure
- HTTP status behavior
- User-Agent expectations
- Rate limits and Retry-After behavior
- Cache directives and provider terms
- Permitted storage and display of returned data

Do not assume every field is always present.

### Provider adapter contract

The provider adapter should return normalized domain objects or explicit provider errors.

It must not return unvalidated arbitrary JSON directly to analytics services.

Recommended error categories:
- `PLAYER_NOT_FOUND`
- `UPSTREAM_RATE_LIMITED`
- `UPSTREAM_TIMEOUT`
- `UPSTREAM_UNAVAILABLE`
- `UPSTREAM_INVALID_RESPONSE`
- `UPSTREAM_FORBIDDEN`
- `UPSTREAM_UNKNOWN_ERROR`

Map actual provider responses carefully. A temporary provider error must not be interpreted as proof that a player does not exist.

## 9. REST API

All routes use `/api/v1`.

### Common conventions

- JSON request and response bodies.
- UTF-8.
- UTC timestamps in ISO 8601 format.
- Stable machine-readable error codes.
- Consistent pagination.
- No internal stack traces in responses.
- Explicit data freshness and completeness metadata where relevant.

### 9.1 `GET /api/v1/players/{username}`

Purpose: resolve and return basic public player information.

Example response:

    {
      "username": "example_player",
      "display_name": null,
      "profile_url": "https://www.chess.com/member/example_player",
      "avatar_url": null,
      "current_rapid_rating": null,
      "data_status": "fresh",
      "last_successful_update": "2026-10-20T10:00:00Z"
    }

Optional fields may be `null` when unavailable.

Do not invent a display name, avatar, or rating.

### 9.2 `GET /api/v1/players/{username}/overview`

Purpose: return the primary 30-day Rapid dashboard.

Example response:

    {
      "username": "example_player",
      "period": {
        "start": "2026-09-20T10:00:00Z",
        "end": "2026-10-20T10:00:00Z",
        "timezone": "UTC"
      },
      "games_count": 42,
      "wins": 22,
      "losses": 16,
      "draws": 4,
      "win_rate": 52.38,
      "current_rating": null,
      "current_streak": {
        "type": "win",
        "length": 3
      },
      "longest_winning_streak": 5,
      "data_status": "partial",
      "missing_sections": ["rating_history"],
      "as_of": "2026-10-20T10:00:00Z",
      "last_successful_update": "2026-10-20T09:45:00Z"
    }

Values above are illustrative, not real provider data.

`data_status` must use a documented enum, such as:
- `fresh`
- `partial`
- `stale`
- `unavailable`

A response may include additional completeness metadata. Do not label a response fresh merely because it came from the database.

### 9.3 `GET /api/v1/players/{username}/rating-history`

Purpose: return available Rapid rating observations within the period.

Optional query parameters:
- `from`: ISO 8601 timestamp
- `to`: ISO 8601 timestamp

Example response:

    {
      "username": "example_player",
      "points": [
        {
          "timestamp": "2026-10-01T10:00:00Z",
          "rating": 1200,
          "source": "game_record"
        }
      ],
      "coverage": "partial",
      "data_status": "partial",
      "last_successful_update": "2026-10-20T09:45:00Z"
    }

The example point is illustrative.

Do not fabricate missing points or promise a complete daily series.

### 9.4 `GET /api/v1/players/{username}/openings`

Purpose: return opening-level statistics.

Optional query parameters:
- `limit`: maximum number of opening groups
- `sort`: documented sort option

Example response:

    {
      "username": "example_player",
      "items": [
        {
          "opening_id": null,
          "name": "Unknown",
          "games_count": 4,
          "wins": 2,
          "losses": 1,
          "draws": 1,
          "win_rate": 50.0
        }
      ],
      "data_status": "fresh"
    }

This example is illustrative.

### 9.5 `GET /api/v1/players/{username}/opponents`

Purpose: return opponent-level statistics.

Optional query parameters:
- `limit`
- `sort`

Each item should expose a stable identifier where available, game count, outcome counts, and win rate.

Sort options must be documented and deterministic. Do not present rating or performance comparisons as statistically conclusive without adequate data.

### 9.6 `GET /api/v1/players/{username}/games`

Purpose: return paginated eligible games.

Query parameters:
- `limit`: bounded page size
- `cursor`: opaque pagination cursor, if cursor pagination is implemented
- `result`: optional outcome filter
- `opening`: optional opening filter, if reliably supported

Do not allow unbounded responses.

Example response:

    {
      "username": "example_player",
      "items": [],
      "next_cursor": null,
      "data_status": "fresh"
    }

### 9.7 `GET /api/v1/players/{username}/games/{game_id}`

Purpose: return an individual game and available details.

The API must verify that the requested game belongs to the resolved player dataset and is eligible for the documented scope.

Return only fields that are available and permitted to expose.

## 10. Error Contract

Use a consistent error envelope:

    {
      "error": {
        "code": "UPSTREAM_UNAVAILABLE",
        "message": "Game data is temporarily unavailable.",
        "request_id": "request-id"
      }
    }

Do not expose internal exception messages.

Recommended status mapping:
- `400 Bad Request`: malformed query or invalid parameter format
- `404 Not Found`: confirmed missing player or game
- `422 Unprocessable Entity`: syntactically valid input that cannot be processed under a documented rule
- `429 Too Many Requests`: application-level rate limit, if one is implemented
- `502 Bad Gateway`: invalid or unexpected upstream response
- `503 Service Unavailable`: upstream unavailable and no usable cached response
- `504 Gateway Timeout`: upstream timeout and no usable cached response

Do not map every upstream failure to `404`.

When cached data is available after an upstream failure, returning a successful response with explicit stale metadata may be preferable to returning an error. This behavior must be consistent across endpoints.

## 11. Database Schema

Use PostgreSQL with SQLAlchemy 2.x and Alembic migrations.

The following is a logical schema. Exact SQL types, indexes, and constraints should be finalized during implementation.

### 11.1 `players`

Purpose: normalized public player records.

Fields:
- `id`: primary key
- `provider`: provider identifier, initially `chess_com`
- `provider_player_id`: stable identifier if the provider supplies one
- `username`: normalized username
- `display_name`: nullable
- `profile_url`: nullable
- `avatar_url`: nullable
- `created_at`
- `updated_at`

Constraints:
- Unique provider plus normalized username, unless a verified stable provider identity model supports a better key.
- Index on normalized username.
- Validate and normalize usernames according to verified provider rules.

Do not assume that username casing or renaming behavior is irrelevant without checking the provider contract.

### 11.2 `games`

Purpose: canonical game records.

Fields:
- `id`: internal primary key
- `provider`: provider identifier
- `provider_game_id`: provider's stable game identifier when available
- `game_url`: nullable
- `played_at`: UTC timestamp
- `time_class`: normalized classification
- `rated`: nullable boolean
- `white_player_id`: nullable FK to players
- `black_player_id`: nullable FK to players
- `white_rating`: nullable integer
- `black_rating`: nullable integer
- `result_white`: normalized outcome from White's perspective, if determinable
- `opening_id`: nullable FK
- `opening_name`: nullable
- `pgn`: nullable text, subject to provider terms and storage policy
- `source_updated_at`: nullable
- `created_at`
- `updated_at`

Constraints and indexes:
- Unique provider plus provider game identifier when the identifier is stable.
- Index on `played_at`.
- Index on `time_class` and `played_at`.
- Indexes on player references.
- Deduplicate games on repeated archive fetches.

Do not make a provider game identifier unique until its uniqueness guarantees have been verified.

### 11.3 `player_games`

Purpose: represent a player's participation in a game and store perspective-specific information.

Fields:
- `id`: primary key
- `player_id`: FK to players
- `game_id`: FK to games
- `color`: `white` or `black`
- `result`: `win`, `loss`, `draw`, or `unknown`
- `rating_before`: nullable integer
- `rating_after`: nullable integer
- `created_at`
- `updated_at`

Constraints:
- Unique `(player_id, game_id)`.
- Index on `(player_id, game_id)` and other query patterns established by profiling.
- Validate consistency between player, color, and game participants.

This table simplifies player-relative statistics and avoids duplicating separate white/black queries in analytics code.

### 11.4 `player_statistics`

Purpose: cache computed aggregates for a player and a defined analysis window.

Fields:
- `id`: primary key
- `player_id`: FK to players
- `period_start`: UTC timestamp
- `period_end`: UTC timestamp
- `metric_version`: string or integer identifying the calculation rules
- `statistics_json`: validated JSONB payload
- `computed_at`
- `source_data_as_of`

Constraints:
- Unique key based on player, period, and metric version.

Do not persist aggregate results without enough information to invalidate or recompute them when the source data or metric rules change.

### 11.5 `cache_metadata`

Purpose: track fetch status and freshness for provider resources.

Fields:
- `id`: primary key
- `player_id`: nullable FK to players
- `resource_type`: documented resource identifier
- `cache_key`: normalized resource key
- `last_attempt_at`
- `last_success_at`: nullable
- `expires_at`: nullable
- `status`: `fresh`, `stale`, `failed`, or equivalent documented state
- `last_error_code`: nullable
- `record_count`: nullable integer
- `created_at`
- `updated_at`

Constraints:
- Unique cache key, or a documented compound key.
- Index on `expires_at`.
- Do not store sensitive raw error payloads.

Cache metadata is not a substitute for validating whether the cached data itself is usable.

### 11.6 Future-only `game_analysis`

Not part of the MVP.

If engine analysis is introduced later, consider a separate table with:
- `game_id`
- engine name and version
- analysis configuration
- analysis status
- completion timestamp
- result payload or normalized analysis records
- failure information

This requires a separate specification, resource budget, and licensing review.

## 12. Caching and Refresh Policy

Use PostgreSQL-backed persistence and cache metadata for the MVP.

Initial proposal: configurable 12-hour TTL for eligible cached resources, subject to provider documentation and observed data-update behavior.

Rules:
1. Serve fresh cached data when valid.
2. Refresh expired or missing data according to a bounded policy.
3. If refresh fails, serve the last known good data when safe.
4. Mark stale data explicitly.
5. Never replace good data with a failed empty response.
6. Respect provider rate limits and cache directives.
7. Avoid duplicate concurrent refreshes for the same cache key where practical.
8. Track the last successful update separately from the last attempted update.
9. Apply timeouts to every outbound HTTP request.
10. Use bounded retries with backoff; respect `Retry-After`.

The 12-hour value is a configurable starting assumption, not a guarantee of provider freshness or a substitute for upstream rules.

## 13. Security and Privacy

- Do not request Chess.com passwords or session cookies.
- Do not implement authentication for the MVP.
- Validate and normalize usernames and game identifiers.
- Use outbound request timeouts.
- Prevent user input from being used as arbitrary URLs or unrestricted hostnames.
- Keep database credentials and secrets in environment variables.
- Avoid logging full PGNs or unnecessary provider payloads.
- Do not expose stack traces, SQL, or internal host information.
- Apply sensible application-level rate limiting if public deployment requires it.
- Use safe HTTP client configuration and prevent server-side request forgery.
- Follow provider terms for public data retrieval, storage, caching, and attribution.
- Provide clear messaging when requested data cannot be retrieved.

## 14. Reliability and Performance

Initial engineering goals, subject to measurement:
- Paginate game results.
- Bound outbound request timeouts.
- Avoid downloading or parsing the same data unnecessarily.
- Index common player/game lookup paths.
- Avoid unbounded memory growth when processing PGN archives.
- Keep individual malformed games isolated.
- Cache reusable normalized records and aggregates.
- Expose enough structured logging to diagnose provider and database failures.

Do not claim performance targets are met until they have been measured in the target environment.

## 15. Frontend Requirements

### Main page
- Username input
- Search action
- Validation feedback
- Loading state
- Clear not-found and upstream-error messages

### Overview
- Eligible game count
- Wins, losses, draws
- Win rate
- Current streak, when determinable
- Longest winning streak
- Rating information when available
- Data freshness and completeness indicator

### Rating history
- Chart of actual available observations
- Date and rating tooltips
- Clear empty and partial-data states
- No invented daily points

### Openings
- Opening name
- Game count
- Outcome breakdown
- Win rate
- Unknown category where needed

### Opponents
- Opponent identifier/name
- Number of games
- Outcome breakdown
- Perspective-correct win rate

### Games
- Paginated list
- Date
- Opponent
- Result
- Available ratings
- Opening where known
- Link to provider game or internal details

### Game details
- Available game metadata
- Available PGN-derived information
- Clear indication when detailed move data is unavailable

All pages must handle loading, empty, partial, stale, and error states. Use responsive layouts and accessible form controls.

## 16. Testing Strategy

### Unit tests
- Outcome normalization
- Win-rate calculation
- Streak calculation
- Window boundaries
- Rapid filtering
- Opening normalization
- Opponent grouping
- Unknown and missing values

### Provider tests
- Valid responses
- Missing optional fields
- Invalid JSON or malformed records
- Confirmed not-found
- Rate limiting
- Timeout
- Provider outage
- Unexpected status codes

### Database tests
- Constraints
- Deduplication
- Upserts
- Transaction rollback
- Cache freshness queries
- Aggregate invalidation

### API tests
- Valid username
- Invalid username
- Unknown player
- Empty dataset
- Partial dataset
- Stale cached response
- Provider unavailable without cache
- Pagination
- Missing game

### Frontend tests
- Search flow
- Input validation
- Loading and error states
- Overview rendering
- Null rating and win rate
- Stale and partial indicators
- Empty charts and lists
- Pagination and game details

The default automated test suite must use mocks, fixtures, and a test database rather than depend on live provider uptime.

## 17. Environment Configuration

Provide `.env.example` with documented non-secret defaults, such as:
- `DATABASE_URL`
- `CHESS_COM_USER_AGENT`, if required
- `REQUEST_TIMEOUT_SECONDS`
- `CACHE_TTL_SECONDS`
- `LOG_LEVEL`
- `CORS_ORIGINS`

Do not commit a populated `.env` containing secrets.

Validate configuration at startup and fail clearly when required settings are missing.

## 18. MVP Release Checklist

- [ ] Backend starts with documented configuration.
- [ ] Database migrations run from a clean database.
- [ ] A visitor can search by Chess.com username.
- [ ] Only eligible Rapid games in the 30-day window are included.
- [ ] Overview metrics are correct and tested.
- [ ] Rating observations are not fabricated.
- [ ] Openings and opponents use validated data.
- [ ] Game history is paginated.
- [ ] Missing and stale data are clearly identified.
- [ ] Provider failures do not destroy last known good data.
- [ ] UI handles empty, partial, loading, and error states.
- [ ] Automated tests pass.
- [ ] Setup and limitations are documented.
- [ ] External provider requirements have been verified.
- [ ] No deferred engine metrics are represented as implemented.

## 19. Open Technical Questions

Resolve these during the provider-integration issue:
- Which official endpoints and fields are currently available for player profiles and Rapid archives?
- What identifiers are stable enough for database deduplication?
- What are the current provider caching, rate-limit, and attribution requirements?
- Which timestamps and rating fields are authoritative?
- Which opening metadata can be obtained reliably?
- What storage and redistribution restrictions apply to PGN and profile fields?
- Does provider data support a sufficiently complete rating-history chart, or should the UI explicitly present a sparse series?

Document verified answers in the repository before depending on them.
- Index on `time_class`.
- Indexes supporting queries by player and date through the player-game relationship.
- Do not store duplicate provider games when archive retrieval overlaps.

A game may be retained for data normalization only if permitted by provider terms. The analytics query must still enforce the 30-day Rapid scope.

### 11.3 `player_games`

Purpose: connect a game to the player whose perspective is used in analytics.

Fields:
- `id`: primary key
- `player_id`: FK to `players`
- `game_id`: FK to `games`
- `player_color`: `white` or `black`
- `player_result`: `win`, `loss`, `draw`, or `unknown`
- `rating_before`: nullable integer
- `rating_after`: nullable integer, only when actually available
- `created_at`
- `updated_at`

Constraints:
- Unique `player_id` plus `game_id`.
- Index on `player_id`.
- Index or composite index supporting date-filtered game retrieval.

Do not derive `rating_after` from an assumed formula. Store it only when the source actually provides a trustworthy value.

### 11.4 `openings`

Purpose: normalize opening identifiers and names.

Fields:
- `id`: primary key
- `source`: nullable string
- `source_opening_id`: nullable string
- `name`: canonical display name
- `eco_code`: nullable string
- `created_at`
- `updated_at`

Constraints:
- A uniqueness rule for source identifiers when present.
- An index on `eco_code` when it is used for lookup.

If opening metadata is missing or unreliable, use a nullable relationship or an explicit unknown grouping in the analytics layer. Do not invent an ECO code.

### 11.5 `player_statistics`

Purpose: optionally persist computed summaries.

Fields:
- `id`: primary key
- `player_id`: FK to `players`
- `period_start`
- `period_end`
- `metric_version`
- `games_count`
- `wins`
- `losses`
- `draws`
- `win_rate`: nullable numeric
- `current_streak_type`: nullable string
- `current_streak_length`: nullable integer
- `longest_winning_streak`: nullable integer
- `computed_at`
- `data_status`

Constraints:
- Unique player, period boundaries, and metric version if this table stores one canonical summary per window.
- Index on player and period end.

Persisting summaries is optional for the first implementation. If added, define invalidation and recomputation rules before relying on them. A moving 30-day window changes even when the underlying games do not.

### 11.6 `cache_metadata`

Purpose: track source freshness and last-known-good data.

Fields:
- `id`: primary key
- `player_id`: nullable FK to `players`
- `resource_type`: e.g. `profile`, `games`, `overview`
- `cache_key`: normalized resource identifier
- `fetched_at`: nullable timestamp of last successful fetch
- `expires_at`: nullable timestamp
- `last_attempt_at`: nullable timestamp
- `last_error_code`: nullable string
- `last_error_at`: nullable timestamp
- `status`: `fresh`, `stale`, `refreshing`, or `unavailable`
- `created_at`
- `updated_at`

Constraints:
- Unique `cache_key`.
- Index on `expires_at` for maintenance queries where appropriate.

This table stores cache metadata, not necessarily the cached payload itself. Actual game/profile data is stored in the domain tables. If raw provider payloads are retained, their schema, size limits, privacy implications, and storage permissions must be reviewed first.

### 11.7 Future `game_analysis` table

Not part of the MVP.

A future engine-analysis stage may require:
- Game reference
- Engine and version
- Analysis settings
- Completion status
- Per-move analysis
- Accuracy calculation version
- Analysis timestamp
- Failure reason

Do not create this table until engine analysis is approved and its data model is specified.

## 12. Data Ingestion and Normalization

Recommended ingestion workflow:

1. Normalize and validate the username.
2. Resolve the player through the provider adapter.
3. Check the cache for reusable profile and game data.
4. Refresh expired data within configured request and rate limits.
5. Retrieve eligible game archives or records through documented interfaces.
6. Validate each record independently.
7. Normalize game identifiers, timestamps, time controls, players, ratings, results, and available opening data.
8. Upsert records using stable provider identifiers.
9. Associate games with the requested player.
10. Calculate analytics from validated eligible records.
11. Return data and explicit freshness/completeness metadata.

### Idempotency

Repeated retrieval of the same provider game must not create duplicate database rows or duplicate counts.

### Transaction behavior

Persist each coherent batch transactionally. If a single game is malformed, log a safe diagnostic and continue processing other valid games where possible.

Do not leave partially written associations that produce duplicate or contradictory results.

### Data retention

Store only data needed for the product and permitted by provider terms. Define a retention and cleanup policy before introducing large-scale historical ingestion.

## 13. Cache and Refresh Strategy

Initial configurable default: 12 hours for reusable provider data, subject to current provider guidance and observed requirements.

This is a project default proposal, not a claim about Chess.com's required or recommended cache duration.

Requirements:
- Respect provider cache directives and rate limits.
- Do not refresh on every dashboard component request independently.
- Reuse normalized data across overview, opening, opponent, and game endpoints.
- Avoid duplicate concurrent refreshes for the same resource where practical.
- Use bounded timeouts and retries.
- Respect `Retry-After` when supplied.
- Preserve last-known-good data after refresh failure.
- Expose the last successful update time.
- Distinguish a confirmed empty result from a failed request.
- Do not cache invalid or unvalidated upstream payloads as successful results.

### Suggested refresh behavior

| Cache state | Behavior |
|---|---|
| Fresh | Serve cached data |
| Expired, refresh succeeds | Store validated updates and serve refreshed data |
| Expired, refresh fails, usable cache exists | Serve stale data with explicit status |
| Cache absent, refresh succeeds | Store and serve data |
| Cache absent, refresh fails | Return a mapped upstream error |
| Provider confirms no games in period | Return an empty valid result |
| Provider response is malformed | Treat as provider/data error, not a valid empty result |

The frontend must not imply that stale cached values are current.

## 14. Frontend Requirements

### 14.1 Main page

Provide:
- Username input
- Search/submit action
- Username validation
- Loading indicator
- Clear error messages
- A primary overview dashboard
- Navigation or sections for ratings, openings, opponents, and games
- Freshness and partial-data indicators

### 14.2 Overview

Display:
- Total eligible games
- Wins, losses, and draws
- Win rate
- Current streak
- Longest winning streak
- Current Rapid rating, if available

All values must be consistent with the API's definitions.

### 14.3 Rating history

Display available rating observations in a chart.

Requirements:
- Label axes and units.
- Show timestamps in a readable local display format while retaining UTC in the API.
- Do not fabricate points for missing dates.
- Show an empty state when no reliable observations exist.
- Indicate incomplete coverage where relevant.

### 14.4 Openings

Display opening name, sample size, outcomes, and win rate.

Requirements:
- Make sample sizes visible.
- Allow deterministic sorting.
- Label unknown openings honestly.
- Avoid claiming that an opening caused a particular result.

### 14.5 Opponents

Display opponent identity, game count, and outcome summary.

Requirements:
- Make the player's perspective clear.
- Avoid merging identities based only on similar names.
- Provide an empty state when no opponent data exists.

### 14.6 Games

Display a paginated list of eligible games.

Where available, show:
- Date
- Opponent
- Outcome
- Player/opponent rating information
- Opening
- Link to the source game

Individual game details must degrade gracefully when PGN or optional fields are unavailable.

### 14.7 Shared data states

Every major data section must handle:
- Loading
- Success
- Empty
- Partial
- Stale
- Error

A failure in the opening-statistics endpoint should not automatically hide a valid overview if the API can serve the overview independently.

Do not show a successful-looking empty chart while data is still loading or unavailable.

## 15. Non-Functional Requirements

### Correctness
- Analytics must be deterministic for identical normalized inputs and metric version.
- The same game must not count twice.
- All relevant endpoints must use consistent filtering and outcome rules.

### Reliability
- Provider failures must be bounded by timeouts.
- Retries must be limited.
- Last-known-good data must survive failed refreshes.
- Invalid individual games must not unnecessarily destroy valid aggregate data.

### Security
- Validate usernames and all external data.
- Use parameterized database operations.
- Keep credentials and database URLs in environment variables.
- Do not expose secrets or stack traces.
- Apply request limits and input length limits.
- Protect against resource exhaustion through bounded page sizes and bounded parsing workloads.

### Performance
- Use indexes for common lookup and time-filtered queries.
- Avoid duplicate upstream requests.
- Keep API responses bounded.
- Measure performance before introducing additional infrastructure.

Numeric latency targets should be established after measuring representative workloads rather than invented without a baseline.

### Accessibility
- Support keyboard navigation.
- Use semantic HTML and accessible labels.
- Ensure charts have a textual summary or accessible data alternative.
- Provide readable contrast and visible focus states.
- Do not rely on color alone to distinguish wins, losses, and draws.

### Observability
- Log request failures and refresh outcomes using structured logs.
- Use a request identifier for troubleshooting.
- Record safe operational metrics such as cache hits, refresh failures, provider latency, and malformed-record counts.
- Never log secrets or unnecessarily retain sensitive request data.

## 16. Testing Strategy

### Unit tests

Cover:
- Username normalization
- Date-window filtering
- Rapid-only filtering
- Outcome normalization
- Win-rate calculation
- Zero-game handling
- Streak calculation
- Opening grouping
- Opponent grouping
- Missing and unknown values

### Provider tests

Use mocked HTTP responses or fixtures to cover:
- Successful player lookup
- Confirmed missing player
- Empty archive
- Mixed eligible and ineligible games
- Missing optional fields
- Malformed records
- Rate limiting
- Timeout
- Server error
- Invalid response format

### Database tests

Cover:
- Uniqueness constraints
- Idempotent upserts
- Player-game associations
- Transaction rollback
- Date-filtered retrieval
- Migration application

### API tests

Cover:
- Valid player
- Invalid username
- Confirmed missing player
- Empty period
- Partial data
- Stale cache
- Provider outage with cache
- Provider outage without cache
- Pagination
- Missing game
- Response schema consistency

### Frontend tests

Cover:
- Search submission
- Validation
- Loading state
- Overview rendering
- Null metrics
- Empty and partial data
- Stale-data warning
- API errors
- Game list and detail navigation

### Integration tests

Use a test PostgreSQL database or a documented test setup. The ordinary test suite must not depend on live Chess.com uptime.

## 17. Configuration and Environment

Provide `.env.example` with documented non-secret defaults.

Potential settings:
- `DATABASE_URL`
- `CHESS_COM_USER_AGENT`, if required by current provider documentation
- `CACHE_TTL_SECONDS`
- `UPSTREAM_TIMEOUT_SECONDS`
- `UPSTREAM_MAX_RETRIES`
- `LOG_LEVEL`
- `CORS_ORIGINS`

Never commit production credentials.

Validate required configuration at startup and fail with a safe, actionable error.

## 18. Deployment and Local Development

The repository should support a documented local development workflow.

Expected setup:
1. Install or start PostgreSQL.
2. Configure environment variables.
3. Install backend dependencies.
4. Run Alembic migrations.
5. Start FastAPI.
6. Install frontend dependencies.
7. Start the Vite development server.
8. Run backend and frontend tests.

Docker Compose may provide PostgreSQL and optional application containers.

The README must document ports, startup commands, migrations, testing, and common configuration issues.

## 19. MVP Release Criteria

The MVP is ready when:

1. A user can submit a valid Chess.com username without registering.
2. The application resolves the player or reports a clear error.
3. Only eligible completed Rapid games from the rolling 30-day period contribute to the analytics.
4. Overview counts and win rate are correct.
5. Streaks are calculated according to the documented rules.
6. Available rating observations are displayed without fabricated values.
7. Opening and opponent statistics are computed from normalized data.
8. Users can browse games and open supported game details.
9. Unknown, empty, stale, partial, and unavailable data are distinguishable.
10. Provider failures do not erase last-known-good data.
11. Automated tests cover the critical analytics and failure cases.
12. The application can be started locally using documented instructions.
13. The provider integration has been checked against current official documentation and applicable terms.
14. No engine-dependent metric is presented as if it were implemented.

## 20. Open Decisions and Verification Items

Resolve these through implementation research or explicit product approval:

- Exact Chess.com endpoints and field availability
- Provider terms, attribution, and caching requirements
- Whether source identifiers are stable enough for the proposed game keys
- Whether sufficient Rapid rating observations exist for useful historical charts
- Which opening mapping source can legally and reliably be used
- Exact cache TTL after reviewing provider guidance
- Whether raw PGN should be stored permanently, temporarily, or fetched on demand
- Whether frontend routing needs a dedicated routing library
- Deployment provider and production resource limits

Do not block unrelated work while investigating a question that affects only a later stage. Record the decision and its consequences before implementing the affected feature.
