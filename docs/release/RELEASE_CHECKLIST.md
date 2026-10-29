# MVP Release Checklist

Date: 2026-10-29 · Scope: Issues 1–10 plus opt-in Stockfish analysis · Verdict:
**releasable for local use** — every automated check, the Docker database, the migrations,
the live Chess.com contract and a real engine analysis have been executed (§1, §3).
Non-blocking gaps: no production deployment target and no CI yet (see
`docs/KNOWN_LIMITATIONS.md`).

## 1. Executed checks (Windows, 2026-10-29)

Environment: Windows 11, Python 3.12.10 (`backend/.venv`), Node 24.22.0 / npm 11.19.1,
PostgreSQL 16.9 in Docker Compose on port **55432**, Docker 29.9.1.

| Check | Command | Result |
| ----- | ------- | ------ |
| Backend lint | `ruff check app tests migrations` | ✅ pass (105 files) |
| Backend format | `ruff format --check .` | ✅ 105 files already formatted |
| Backend types | `mypy` (strict) | ✅ pass (104 source files) |
| Full backend suite, with PostgreSQL | `pytest` | ✅ **409 passed** |
| Backend suite without PostgreSQL | `pytest` | ✅ unit tests pass; DB tests skip cleanly |
| Migrations on the development database | `alembic current` | ✅ `0003 (head)` |
| Model/migration drift | `alembic check` | ✅ no changes detected |
| Frontend unit/component tests | `npm run test` (Vitest 4.1.12) | ✅ **23 passed** (2 files) |
| Frontend lint | `npm run lint` | ✅ 0 errors, 0 warnings |
| Frontend format | `npm run format:check` | ✅ all files match Prettier |
| Frontend types | `npm run typecheck` | ✅ clean (`tsconfig` + `tsconfig.node`) |
| Frontend production build | `npm run build` | ✅ built in ~13 s; one 657.65 kB chunk (194.64 kB gzip) → Vite chunk-size warning only |
| Frontend dependency audit | `npm audit` | ✅ **0 vulnerabilities** (after the Vitest 4.1.12 upgrade) |
| Docker database | `docker compose up -d db` | ✅ `postgres:16.9-alpine`, healthy, `127.0.0.1:55432` |
| Live Chess.com contract | real requests for `olzhaswlk` | ✅ profile, stats, archives, 2026/09 and 2026/10 archives all `200` |
| Live end-to-end UI | browser at `http://localhost:5173` | ✅ search → overview → all tabs → pagination → filter → game details → back |

Backend suite history: the 2026-10-20 sandbox run recorded 356 passed; the suite grew to
361 (restored Issue 1 files), to 368 after the opening-name normalization tests, to
399 after engine analysis (accuracy math, per-game analysis, API + worker integration),
and to 409 after the cross-game form report.

## 2. Live data verification (2026-10-29)

`GET /api/v1/players/olzhaswlk/overview` against the real PubAPI:

| Field | Value |
| ----- | ----- |
| `games_count` | 43 |
| `wins` / `losses` / `draws` | 23 / 18 / 2 |
| `win_rate` | 53.49 |
| `current_rating` | 756 (`provider_stats`) |
| `data_status` | `fresh` |

Ingestion log for the same refresh: `eligible_games=43`,
`excluded={'outside_window': 21, 'not_rapid': 58}`, `months_failed={}`.

Browser walkthrough (same player): rating history chart and its table alternative,
openings table with sample sizes, opponents table with perspective labels, game list with
cursor pagination and result filter, game details with the full PGN (57 plies), and the
"Back to games" button returning to the same page and filter.

## 3. Engine analysis verification (2026-10-29)

Stockfish **19** (`winget install Stockfish.Stockfish`, path in `.env`
`STOCKFISH_PATH`), fixed profile depth 12 / 1 thread / 64 MB hash. The API only
enqueues; `python -m app.worker --once` performs the search.

| Check | Result |
| ----- | ------ |
| Accuracy math (win probability, per-move accuracy, CPL, thresholds) | ✅ 21 pure unit tests (incl. UCI parsing) |
| Per-game analysis with a deterministic fake engine | ✅ 7 unit tests (all-best, blunders, mate mapping, unusable PGN codes) |
| API + worker integration on PostgreSQL | ✅ 3 tests: request → queued → worker → completed → cached; repeat POST reuses the result; unknown game `404 GAME_NOT_FOUND`; missing PGN → `failed` + `missing_pgn` |
| Worker queue claim | ✅ `FOR UPDATE SKIP LOCKED`, `attempts` counter, stale-job requeue SQL |
| Real game `live:186123080328` (player Black) | ✅ completed in **6.8 s** |
| White (opponent) accuracy / ACPL | 84.98% / 149.65 (13 blunders) |
| Black (player) accuracy / ACPL | 86.19% / 132.96 |
| Engine identity recorded in the payload | ✅ `{"name": "Stockfish", "version": "19", "depth": 12}` |
| Browser check of the panel | ✅ cached result rendered (86.2% / 85.0%), key moments listed, no console errors |
| Cache behaviour | ✅ second `POST` returns the stored analysis without a new job |

## 3b. Cross-game form report verification (2026-10-29)

`POST /form/analyze` queued **42** remaining games (`games_total: 43`),
`python -m app.worker --drain` completed all of them (≈ 5–10 s per game), and
`GET /form` then returned full coverage.

| Check | Result |
| ----- | ------ |
| Backend tests (form analytics + API) | ✅ 9 pure + 1 integration test; full suite **409 passed** |
| Frontend tests (form tab) | ✅ **23 passed** (2 files), lint/format/typecheck clean |
| Empty report (1 analysed game) | ✅ `primary_leak: null`, phase groups labelled, no Elo wording |
| Batch request | ✅ `{games_total: 43, already_analyzed: 1, queued: 42, pending: 42}` |
| Worker drain | ✅ 42 jobs completed, 0 failed, queue empty |
| Full report | ✅ 43/43 analysed; accuracy 87.4%, ACPL 94.67, 163.4 wp points / game |
| Primary leak on the live account | ✅ `As White` — 177.5 points/game over 22 games (123 blunders) |
| Top openings | ✅ four openings at ≥ 2 games, ranked by loss/game (Modern Defense 237.7) |
| Browser check | ✅ headline, trend chart, phase/colour/opening tables, top moments with game links; no console errors |
| Sample-size honesty | ✅ openings with 2 games never named primary leak; report states "43 of 43 eligible games analysed" |

Definitions live in `spec.md` §6.10 and `AGENT.md`: accuracy is the mean per-move
retention of the engine's win probability (documented Lichess formula), and **no rating
is estimated from it**. The UI says "mean move accuracy" and states that labels use fixed
centipawn-loss thresholds.

## 4. End-to-end verification (automated)

`tests/db/test_e2e_primary_flow.py` runs HTTP API → cache policy → ingestion → the
real Chess.com adapter (HTTP replaced by `httpx.MockTransport`) → PostgreSQL →
analytics.

| Scenario | Verified |
| -------- | -------- |
| Search → overview → games → game detail → openings → opponents → rating history | ✅ |
| Overview equals hand-calculated values from `archive_mixed.json` (14 records, 2 eligible: 1 win, 1 unknown → win rate 100.00, streak win×1, `streak_may_be_incomplete`) | ✅ |
| Repeated search (different casing) served from cache with **zero** upstream requests | ✅ |
| Provider 503 / 429 (Retry-After 120) / timeout **with** cache → `200`, `data_status: stale`, last good data and timestamp kept | ✅ |
| Same failures **without** cache → `503` / `503` / `504` error envelope, never an empty dataset; `Retry-After` honoured | ✅ |
| Confirmed missing player → `404 PLAYER_NOT_FOUND` | ✅ |
| Error bodies contain no traceback, library names, provider URL or DB URL | ✅ |

## 5. spec.md §19 release criteria

| # | Criterion | Status | Evidence |
| - | --------- | ------ | -------- |
| 1 | Search without registration | ✅ | No auth anywhere; `App.tsx`, API |
| 2 | Player resolved or clear error | ✅ | 400 / 404 / 502–504 envelope (`api-overview.md`) |
| 3 | Only eligible Rapid games, rolling 30 days | ✅ | `eligibility.py`, `window.py`, boundary tests, live `excluded` counts |
| 4 | Correct counts and win rate | ✅ | analytics unit tests + E2E hand calculation + live overview |
| 5 | Streaks per documented rules | ✅ | `analytics/overview.py`, tests |
| 6 | Rating observations without fabrication | ✅ | `rating_history`, tests; semantics labelled |
| 7 | Opening and opponent statistics | ✅ | Issue 7 tests, live UI |
| 8 | Browse games and details | ✅ | `App.test.tsx` + live walkthrough (PGN, pagination, filter) |
| 9 | Unknown/empty/stale/partial/unavailable distinguishable | ✅ | cache + API tests + UI state tests |
| 10 | Provider failures keep last-known-good data | ✅ | `test_cache.py`, E2E |
| 11 | Automated tests for analytics and failures | ✅ | 409 backend + 23 frontend tests |
| 12 | Local start with documented instructions | ✅ | README; Compose, both dev servers and the analysis worker executed |
| 13 | Provider checked against official docs and terms | ✅ | `chess-com-provider.md`; live requests on 2026-10-29 |
| 14 | No unverified engine metric presented | ✅ | Provider `accuracies` still ignored; the only engine numbers are produced by Stockfish with documented definitions (§3) and are labelled as such |

## 6. Security and operations review

| Area | Finding |
| ---- | ------- |
| Secrets | `DATABASE_URL` is `SecretStr`; config errors name variables, never values; `.env` ignored by git |
| Logs | 3 log statements (provider retry, ingestion summary, cache outcome): usernames, error codes, counts only; no payloads, URLs with credentials or exception text |
| Error responses | Fixed messages + codes; `request_id` accepted only if alphanumeric/hyphen ≤ 64 chars |
| Input validation | Username `[A-Za-z0-9_-]{1,64}` before any request; `limit` 1–100; cursors validated and bound to filters; `from`/`to` require a time zone and cannot widen the window |
| Resource bounds | HTTP timeouts, ≤ 2 retries, 60 s budget per request, 25 MiB response cap (after gzip), PGN ≤ 100 000 chars / 1 000 plies, batched SQL writes; analysis capped at 400 plies and 30 s per engine search |
| Upstream etiquette | Serial requests, 12 h TTL, cooldown ≥ max(300 s, Retry-After), advisory lock against duplicate refreshes |
| CORS | Explicit origins, `GET` and `POST` (analysis requests) |

## 7. Remaining before a public deployment

1. Set `CHESS_COM_USER_AGENT` with real contact information.
2. Compare `backend/tests/providers/fixtures/` field by field with one real response per
   endpoint (the live contract is confirmed, the fixtures are still synthetic).
3. Add CI (GitHub Actions) running the backend and frontend checks.
4. Choose a deployment target and serve the built frontend from the same origin
   (`VITE_API_BASE_URL` empty) or an origin listed in `CORS_ORIGINS`.
5. Consider code-splitting the frontend bundle (Recharts accounts for most of the
   657.65 kB single chunk).
6. Install Stockfish on the deployment host (or set `STOCKFISH_PATH`), run at least one
   `python -m app.worker` process, and monitor the queue; without a worker, analyses stay
   `queued` forever.

## 8. Dependency versions actually installed

Backend: SQLAlchemy 2.1.5, Alembic 1.20.0, psycopg 3.3.6, FastAPI 0.149.0,
pydantic 2.14.1, pydantic-settings 2.16.0, httpx 0.28.1, chess 1.11.2, pytest 9.1.1,
ruff 0.17.1, mypy 2.4.0. Engine: Stockfish 19 (external binary, not a Python dependency).

Frontend: React 19.2, Vite 7.3.7, TypeScript 5.9, Tailwind CSS 4.1, Recharts 3.2,
Vitest 4.1.12, ESLint 9.35, Prettier 3.6. Exact versions are in
`frontend/package-lock.json` (committed).
