# MVP Release Checklist

Date: 2026-10-20 · Scope: Issues 1–10 · Verdict: **not yet releasable** — backend verified;
frontend tests, Docker Compose and the live Chess.com contract must be run by the team
(items marked ⚠ below). No check is reported as passing unless it was executed.

## 1. Executed checks (sandbox, 2026-10-20)

Environment: Python 3.13, PostgreSQL 16.15 (local server), dependencies from source tags
because PyPI/npm were unreachable (versions in §4).

| Check | Command | Result |
| ----- | ------- | ------ |
| Backend lint | `ruff check .` / `ruff format --check .` | ✅ pass (84 files) |
| Backend types | `mypy` (strict) | ✅ pass (83 files) |
| Full backend suite, with PostgreSQL | `pytest` | ✅ **356 passed** |
| Backend suite without PostgreSQL | `pytest` | ✅ 205 passed, 151 skipped (DB tests skip cleanly) |
| Clean-database migration | `alembic upgrade head` on a new DB | ✅ `0001` → `0002`, `alembic current` = `0002 (head)` |
| Model/migration drift | `alembic check` | ✅ no changes detected |
| Downgrade and re-upgrade | `alembic downgrade base` → `upgrade head` | ✅ |
| Offline SQL | `alembic upgrade head --sql` | ✅ 5 tables + 9 indexes emitted |
| End-to-end primary flow | `tests/db/test_e2e_primary_flow.py` | ✅ 9 passed (see §2) |
| Frontend type check | `tsc --strict` with React 19 types; vitest/RTL/recharts stubbed | ✅ app code; 4 errors only in the test file caused by the stubs |
| Frontend production bundle | esbuild with a recharts stub | ✅ 214 KiB |
| Frontend render smoke | react-dom/server on key components | ✅ 7/7 (nulls as "—", stale banner, empty chart, Unknown opening) |
| ⚠ Frontend test suite | `npm run test` (Vitest + RTL) | **not run** — npm registry unreachable |
| ⚠ Frontend lint / typecheck / build | `npm run lint && npm run typecheck && npm run build` | **not run** — same reason |
| ⚠ Docker Compose | `docker compose up -d db` | **not run** — no Docker daemon in sandbox |
| ⚠ Live Chess.com contract | one real response per endpoint vs fixtures | **not run** — api.chess.com unreachable |

## 2. End-to-end verification

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

## 3. spec.md §19 release criteria

| # | Criterion | Status | Evidence |
| - | --------- | ------ | -------- |
| 1 | Search without registration | ✅ | No auth anywhere; `App.tsx`, API |
| 2 | Player resolved or clear error | ✅ | 400 / 404 / 502–504 envelope (`api-overview.md`) |
| 3 | Only eligible Rapid games, rolling 30 days | ✅ | `eligibility.py`, `window.py`, boundary tests |
| 4 | Correct counts and win rate | ✅ | analytics unit tests + E2E hand calculation |
| 5 | Streaks per documented rules | ✅ | `analytics/overview.py`, tests |
| 6 | Rating observations without fabrication | ✅ | `rating_history`, tests; semantics labelled |
| 7 | Opening and opponent statistics | ✅ | Issue 7 tests |
| 8 | Browse games and details | ✅ backend · ⚠ UI tests not run | Issue 8 tests; `App.test.tsx` written |
| 9 | Unknown/empty/stale/partial/unavailable distinguishable | ✅ backend · ⚠ UI tests not run | cache + API tests; SSR smoke |
| 10 | Provider failures keep last-known-good data | ✅ | `test_cache.py`, E2E |
| 11 | Automated tests for analytics and failures | ✅ | 356 backend tests |
| 12 | Local start with documented instructions | ⚠ | README; Compose not executed here |
| 13 | Provider checked against official docs and terms | ✅ docs · ⚠ live responses | `chess-com-provider.md` |
| 14 | No engine metric presented as implemented | ✅ | `accuracies` ignored by the adapter; no such field in API/UI (grep verified) |

## 4. Security and operations review

| Area | Finding |
| ---- | ------- |
| Secrets | `DATABASE_URL` is `SecretStr`; config errors name variables, never values; `.env` ignored by git |
| Logs | 3 log statements (provider retry, ingestion summary, cache outcome): usernames, error codes, counts only; no payloads, URLs with credentials or exception text |
| Error responses | Fixed messages + codes; `request_id` accepted only if alphanumeric/hyphen ≤ 64 chars |
| Input validation | Username `[A-Za-z0-9_-]{1,64}` before any request; `limit` 1–100; cursors validated and bound to filters; `from`/`to` require a time zone and cannot widen the window |
| Resource bounds | HTTP timeouts, ≤ 2 retries, 60 s budget per request, 25 MiB response cap (after gzip), PGN ≤ 100 000 chars / 1 000 plies, batched SQL writes |
| Upstream etiquette | Serial requests, 12 h TTL, cooldown ≥ max(300 s, Retry-After), advisory lock against duplicate refreshes |
| CORS | Explicit origins, GET only |

## 5. Release steps

1. Use the complete repository archive (`chesspulse-complete.zip`); the Issue 1 files that
   were missing were rebuilt (backend core files, frontend tooling configuration).
2. `cd frontend && npm install`, then
   `npm run test && npm run lint && npm run typecheck && npm run build`. Record results here.
   Frontend dependency ranges in `package.json` were chosen without registry access;
   `npm install` writes the exact versions to `package-lock.json` — commit it.
3. `docker compose up -d db && cd backend && alembic upgrade head && pytest`.
4. Fetch one real response per PubAPI endpoint for a test account and compare with
   `backend/tests/providers/fixtures/`; update fixtures if fields differ.
5. Set `CHESS_COM_USER_AGENT` with real contact information.
6. Pin exact dependency versions actually installed (sandbox used the source versions
   below; pydantic 2.13.5, ruff 0.16.9 and mypy 2.3.1 differed from the pins).

Sandbox dependency versions: SQLAlchemy 2.1.5, Alembic 1.20.0, psycopg 3.3.6,
FastAPI 0.149.0, pydantic-settings 2.16.0, httpx 0.28.1, chess 1.11.2, pytest 9.1.1.
