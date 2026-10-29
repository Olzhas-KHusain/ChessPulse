# MVP Release Checklist

Date: 2026-10-29 · Scope: Issues 1–10 · Verdict: **releasable for local use** — every
automated check, the Docker database, the migrations and the live Chess.com contract have
been executed (§1). Non-blocking gaps: no production deployment target and no CI yet
(see `docs/KNOWN_LIMITATIONS.md`).

## 1. Executed checks (Windows, 2026-10-29)

Environment: Windows 11, Python 3.12.10 (`backend/.venv`), Node 24.22.0 / npm 11.19.1,
PostgreSQL 16.9 in Docker Compose on port **55432**, Docker 29.9.1.

| Check | Command | Result |
| ----- | ------- | ------ |
| Backend lint | `ruff check .` | ✅ pass (84 files) |
| Backend format | `ruff format --check .` | ✅ 85 files already formatted |
| Backend types | `mypy` (strict) | ✅ pass (84 files) |
| Full backend suite, with PostgreSQL | `pytest` | ✅ **368 passed** |
| Backend suite without PostgreSQL | `pytest` | ✅ unit tests pass; DB tests skip cleanly |
| Migrations on the development database | `alembic current` | ✅ `0002 (head)` |
| Model/migration drift | `alembic check` | ✅ no changes detected |
| Frontend unit/component tests | `npm run test` (Vitest 4.1.12) | ✅ **21 passed** (2 files) |
| Frontend lint | `npm run lint` | ✅ 0 errors, 0 warnings |
| Frontend format | `npm run format:check` | ✅ all files match Prettier |
| Frontend types | `npm run typecheck` | ✅ clean (`tsconfig` + `tsconfig.node`) |
| Frontend production build | `npm run build` | ✅ built in ~11 s; one 606.9 kB chunk (183.2 kB gzip) → Vite chunk-size warning only |
| Frontend dependency audit | `npm audit` | ✅ **0 vulnerabilities** (after the Vitest 4.1.12 upgrade) |
| Docker database | `docker compose up -d db` | ✅ `postgres:16.9-alpine`, healthy, `127.0.0.1:55432` |
| Live Chess.com contract | real requests for `olzhaswlk` | ✅ profile, stats, archives, 2026/09 and 2026/10 archives all `200` |
| Live end-to-end UI | browser at `http://localhost:5173` | ✅ search → overview → all tabs → pagination → filter → game details → back |

Backend suite history: the 2026-10-20 sandbox run recorded 356 passed; the suite grew to
361 (restored Issue 1 files) and to 368 after the opening-name normalization tests.

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

## 3. End-to-end verification (automated)

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

## 4. spec.md §19 release criteria

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
| 11 | Automated tests for analytics and failures | ✅ | 368 backend + 21 frontend tests |
| 12 | Local start with documented instructions | ✅ | README; Compose and both dev servers executed |
| 13 | Provider checked against official docs and terms | ✅ | `chess-com-provider.md`; live requests on 2026-10-29 |
| 14 | No engine metric presented as implemented | ✅ | `accuracies` ignored by the adapter; no such field in API/UI (grep verified) |

## 5. Security and operations review

| Area | Finding |
| ---- | ------- |
| Secrets | `DATABASE_URL` is `SecretStr`; config errors name variables, never values; `.env` ignored by git |
| Logs | 3 log statements (provider retry, ingestion summary, cache outcome): usernames, error codes, counts only; no payloads, URLs with credentials or exception text |
| Error responses | Fixed messages + codes; `request_id` accepted only if alphanumeric/hyphen ≤ 64 chars |
| Input validation | Username `[A-Za-z0-9_-]{1,64}` before any request; `limit` 1–100; cursors validated and bound to filters; `from`/`to` require a time zone and cannot widen the window |
| Resource bounds | HTTP timeouts, ≤ 2 retries, 60 s budget per request, 25 MiB response cap (after gzip), PGN ≤ 100 000 chars / 1 000 plies, batched SQL writes |
| Upstream etiquette | Serial requests, 12 h TTL, cooldown ≥ max(300 s, Retry-After), advisory lock against duplicate refreshes |
| CORS | Explicit origins, GET only |

## 6. Remaining before a public deployment

1. Set `CHESS_COM_USER_AGENT` with real contact information.
2. Compare `backend/tests/providers/fixtures/` field by field with one real response per
   endpoint (the live contract is confirmed, the fixtures are still synthetic).
3. Add CI (GitHub Actions) running the backend and frontend checks.
4. Choose a deployment target and serve the built frontend from the same origin
   (`VITE_API_BASE_URL` empty) or an origin listed in `CORS_ORIGINS`.
5. Consider code-splitting the frontend bundle (Recharts accounts for most of the
   606.9 kB single chunk).

## 7. Dependency versions actually installed

Backend: SQLAlchemy 2.1.5, Alembic 1.20.0, psycopg 3.3.6, FastAPI 0.149.0,
pydantic 2.14.1, pydantic-settings 2.16.0, httpx 0.28.1, chess 1.11.2, pytest 9.1.1,
ruff 0.17.1, mypy 2.4.0.

Frontend: React 19.2, Vite 7.3.7, TypeScript 5.9, Tailwind CSS 4.1, Recharts 3.2,
Vitest 4.1.12, ESLint 9.35, Prettier 3.6. Exact versions are in
`frontend/package-lock.json` (committed).
