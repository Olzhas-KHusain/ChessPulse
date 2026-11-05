# ChessPulse

Web application for analyzing a Chess.com player's standard-chess games (Rapid, Blitz,
Bullet and Daily) over a selectable window of 7 to 365 days, plus a free analysis board
for arbitrary positions. The stored dataset covers `DATASET_WINDOW_DAYS` (90 by
default) of every time class; each request narrows it by `time_class` and `days` at read
time, so no scope needs its own fetch or cache key.

This repository contains the **development environment, database schema, Chess.com
provider adapter, ingestion, cache policy, the player endpoints**
`GET /api/v1/players/{username}/overview`, `/rating-history`, `/openings`, `/opponents`,
`/games`, `/games/{game_id}` and `/form`, the **board endpoints**
`POST /api/v1/board/evaluate` and `/board/move`, the **React dashboard** (search,
overview, cross-game form report, rating chart, openings, opponents, paginated games,
game details with opt-in Stockfish analysis), a **free board** (place any pieces, play
legal moves, engine classification) and a **dark/light theme**.

Engineering rules: `AGENT.md`. Workflow: `process.md`. Roles: `roles/` (product
manager, DevOps engineer, UI/UX developer). Product and technical
specification: `spec.md`. Feature specifications: `docs/specs/` (database schema,
Chess.com provider, ingestion, cache policy, overview, breakdown, games, engine analysis,
free board and form report APIs, frontend dashboard). Architecture decisions:
`docs/adr/`.

## Stack

| Part     | Technology                                                       |
| -------- | ---------------------------------------------------------------- |
| Frontend | React 19, TypeScript (strict), Vite 7, Tailwind CSS 4, Vitest    |
| Backend  | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 (sync), Alembic |
| Database | PostgreSQL 16 (Docker Compose, local development only)           |

## Repository layout

```
backend/     FastAPI modular monolith (app/, migrations/, tests/)
frontend/    React + Vite application (src/)
docs/specs/  Feature specifications (database-schema.md, api-*.md)
roles/       Role operating manuals (pm, devops-engineer, ui-ux-developer)
docker-compose.yml   Full stack: app (static FE + API) + worker + db
infra/               AWS CloudFormation template + deploy notes
render.yaml          Render blueprint (PaaS)
.github/workflows/   CI/CD (tests → e2e → build → deploy)
.env.example         Configuration template (copy to .env)
```

## Prerequisites

- Python 3.12 or 3.13
- Node.js 20.19+ (22 recommended; see `frontend/.nvmrc`) and npm
- Docker with Compose v2 (for local PostgreSQL)

## First-time setup

```bash
# 1. Configuration (never commit .env)
cp .env.example .env

# 2. Database
docker compose up -d db
docker compose ps            # wait until the db service is "healthy"

# 3. Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head         # creates/updates the schema (revisions 0001–0004)
cd ..

# 4. Frontend (first time: npm install creates package-lock.json; commit it, later use npm ci)
cd frontend
npm install
cd ..
```

## Running

Backend (http://localhost:8000, interactive docs at `/docs` outside production):

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:create_app --factory --reload
```

Frontend (http://localhost:5173; `/health` and `/api/*` are proxied to the backend):

```bash
cd frontend
npm run dev
```

Health check:

```bash
curl http://localhost:8000/health
# {"status":"ok","service":"chesspulse-backend","version":"0.1.0","environment":"development"}
```

`GET /health` is an unversioned liveness endpoint; it does not query the database.
Business endpoints live under `/api/v1`.

### Engine analysis worker

Engine analysis is asynchronous. The API only enqueues a job; a separate worker
process runs Stockfish and stores the result.

```bash
winget install Stockfish.Stockfish          # Windows; or install Stockfish another way
# .env: STOCKFISH_PATH=C:\...\stockfish.exe (empty = search PATH)

cd backend
source .venv/bin/activate
python -m app.worker                        # loop forever
python -m app.worker --once                 # process at most one job
python -m app.worker --drain                # process the queue, then exit
```

The worker claims jobs with `FOR UPDATE SKIP LOCKED`, so several workers can run in
parallel without sharing a game. Results are cached per `(game, profile)`, where the
profile is the configured depth, thread count and hash size.

Endpoints:

- `POST /api/v1/players/{username}/games/{game_id}/analysis` — request (idempotent;
  returns the cached result when it already exists).
- `GET  /api/v1/players/{username}/games/{game_id}/analysis` — current state
  (`missing`, `queued`, `running`, `completed`, `failed`) and the payload when done.
- `POST /api/v1/players/{username}/form/analyze` — queue every game in the current
  scope that has no stored analysis.
- `GET  /api/v1/players/{username}/form` — cross-game report: accuracy trend, win
  probability lost per game, leaks by phase/colour/opening and the most expensive moves.

### Free board

The free board does not read the player dataset. It runs the same Stockfish binary
synchronously for one position:

- `POST /api/v1/board/evaluate` — `{"fen": "..."}` → evaluation, game status and the
  engine's best move.
- `POST /api/v1/board/move` — `{"fen": "...", "move_uci": "e2e4"}` → the resulting FEN,
  centipawn loss and classification (`best`, `good`, `inaccuracy`, `mistake`, `blunder`),
  plus the best move before and after the played move.

Both endpoints validate the FEN and the move; details and error codes are in
`docs/specs/api-board.md`. The engine identity and depth are part of every response.

### Windows notes (Git Bash + Docker Desktop)

- Activate the virtual environment with `source .venv/Scripts/activate` (not
  `.venv/bin/activate`); the interpreter is `backend/.venv/Scripts/python.exe`.
- `python3` may be the Microsoft Store placeholder. Use `python` inside the activated
  environment, or `py -3.12` when creating it.
- Write `127.0.0.1` in `DATABASE_URL`, not `localhost`: on Windows `localhost` resolves to
  IPv6 `::1` first, Docker publishes the port on IPv4 only, and Alembic then hangs.
- If port 5432 is already used by a local PostgreSQL, keep `POSTGRES_PORT=55432` (the
  default in `.env.example`) and use the same port in `DATABASE_URL`.
- npm 11 does not run dependency install scripts by default. If Vite fails with an
  esbuild error, run `npm install-scripts approve esbuild && npm rebuild esbuild`.
- Docker Desktop must be running before `docker compose up -d db`; `docker compose ps`
  should report the `db` service as `healthy`.

## Configuration

All settings come from environment variables (or the repository-root `.env`).
Environment variables take precedence over `.env`. Invalid configuration stops startup
with a message that names the variable but never prints its value.

| Variable                         | Required | Description                                                    |
| -------------------------------- | -------- | -------------------------------------------------------------- |
| `DATABASE_URL`                   | yes      | `postgresql+psycopg://user:password@host:port/dbname`          |
| `APP_ENV`                        | no       | `development` (default), `test`, `production`                  |
| `LOG_LEVEL`                      | no       | `INFO` (default), `DEBUG`, `WARNING`, `ERROR`, `CRITICAL`      |
| `CORS_ORIGINS`                   | no       | Comma-separated explicit origins, no wildcard                  |
| `TEST_DATABASE_URL`              | no       | PostgreSQL server for database tests (process env only)        |
| `CHESS_COM_USER_AGENT`           | no       | User-Agent for Chess.com; include contact info in production   |
| `UPSTREAM_TIMEOUT_SECONDS`       | no       | Per-request timeout, `10` by default (0 < value ≤ 60)          |
| `UPSTREAM_MAX_RETRIES`           | no       | Extra attempts for transient failures, `2` by default (0–5)    |
| `UPSTREAM_MAX_RETRY_AFTER_SECONDS` | no     | Longest Retry-After/backoff waited, `10` by default (0–120)    |
| `CACHE_TTL_SECONDS`              | no       | Dataset freshness, `43200` (12 h) by default                   |
| `REFRESH_FAILURE_COOLDOWN_SECONDS` | no     | Wait after a failed refresh, `300` by default                  |
| `DATASET_WINDOW_DAYS`            | no       | Stored window for all classes, `90` by default (30–730)        |
| `STOCKFISH_PATH`                 | no       | Stockfish executable; empty = search `PATH`                    |
| `STATIC_DIR`                     | no       | Built frontend directory; empty = API only (dev mode)          |
| `ANALYSIS_DEPTH`                 | no       | Fixed search depth, `12` by default (6–30)                     |
| `ANALYSIS_THREADS` / `ANALYSIS_HASH_MB` | no | Engine threads (`1`) and hash size (`64`)                    |
| `ANALYSIS_JOB_MAX_ATTEMPTS`      | no       | Claims before a failing job stays failed, `3` by default       |
| `POSTGRES_USER/PASSWORD/DB/PORT` | compose  | Used by `docker-compose.yml`; keep in sync with `DATABASE_URL` |
| `VITE_DEV_PROXY_TARGET`          | no       | Backend URL for the Vite dev proxy                             |
| `VITE_API_BASE_URL`              | no       | API base URL for built bundles (empty = same origin)           |

The values in `.env.example` are local-development placeholders, not real credentials.

## Database schema and migrations (Alembic)

The schema has seven tables: `players`, `games`, `player_games`, `openings`,
`cache_metadata`, `analysis_jobs`, `game_analysis`. `players` stores the provider's
current rating for each class (`current_rapid_rating`, `current_blitz_rating`,
`current_bullet_rating`, `current_daily_rating`, each with its `*_at` timestamp).
Keys, constraints, deletion rules, UTC handling, and the differences from `spec.md` are
documented in `docs/specs/database-schema.md`.

Run from `backend/` with the virtual environment active. The URL is read from
`DATABASE_URL`, not from `alembic.ini`.

```bash
alembic upgrade head                                   # apply all migrations
alembic current                                        # show the applied revision
alembic check                                          # fail if models and migrations differ
alembic downgrade -1                                   # roll back one migration
alembic downgrade base                                 # remove the whole schema (deletes data)
alembic upgrade head --sql                             # print SQL without connecting
```

Changing the schema:

1. Edit or add models in `backend/app/models/` (new models must be imported in
   `app/models/__init__.py`).
2. `alembic revision --autogenerate -m "describe change"`.
3. Review the generated file. Autogenerate does not detect triggers or functions, and it
   renders each enum `CHECK` constraint twice; fix both by hand.
4. `alembic upgrade head`, then `alembic check` and `pytest -m integration`.

All timestamps are stored as `TIMESTAMP WITH TIME ZONE` in UTC. Application code must
pass timezone-aware datetimes; naive datetimes are rejected.

## Tests and quality checks

Backend (from `backend/`, venv active):

```bash
pytest                    # unit tests; database tests are skipped if PostgreSQL is unreachable
pytest -m integration     # only the database tests (migrations, constraints, repositories)
ruff check .              # lint
ruff format --check .     # formatting
mypy                      # type checking (strict)
```

Database tests create a temporary database (`chesspulse_test_<random>`) on the server
from `TEST_DATABASE_URL`, or from `DATABASE_URL` when it is unset, migrate it with
Alembic, and drop it at the end. Your development data is never modified. The role needs
the `CREATEDB` privilege; the Docker Compose user has it. To run them:

```bash
docker compose up -d db
cd backend && pytest -m integration
```

Frontend (from `frontend/`):

```bash
npm run test              # Vitest
npm run lint              # ESLint
npm run format:check      # Prettier
npm run typecheck         # tsc
npm run build             # type-check + production build
```

The standard test suite needs neither network access nor a live Chess.com account:
provider tests use `httpx.MockTransport` with synthetic fixtures in
`backend/tests/providers/fixtures/`.

## Chess.com provider

`backend/app/providers/chess_com/` wraps four documented PubAPI endpoints (profile,
stats, archive list, monthly archive) with timeouts, bounded retries, `Retry-After`
handling and validation of every field. Verified contract, error mapping and known
limitations: `docs/specs/chess-com-provider.md`. Set `CHESS_COM_USER_AGENT` to a value
with contact information, as Chess.com recommends, for example
`ChessPulse/0.1 (contact: you@example.com)`.

## Known limitations and release status

- Release checklist with the checks actually executed: `docs/release/RELEASE_CHECKLIST.md`.
- Known limitations and deferred (non-MVP) features: `docs/KNOWN_LIMITATIONS.md`.
- Data freshness: player data is cached for 12 hours; every API response states
  `data_status` (`fresh`, `partial`, `stale`) and `last_successful_update`.
- Every player endpoint accepts `time_class` (`rapid`, `blitz`, `bullet`, `daily`,
  `all`; default `rapid`) and `days` (7, 30, 90, 180, 365; default 30). Both only
  narrow the stored dataset. `days` cannot exceed `DATASET_WINDOW_DAYS`.
- Engine metrics (accuracy, centipawn loss, move classification) are implemented for
  individual games and the cross-game form report, and are exposed by the free board.

## Containerization and deployment

One Dockerfile builds the frontend and serves it plus the API from a single image:

```bash
docker build -t chesspulse/app .
docker compose up -d --build --wait   # app + worker + db (PostgreSQL 16)
curl http://localhost:8000/health     # app serves the SPA and the API on :8000
```

- `DATABASE_URL` in the container points at the `db` service; migrations
  (`alembic upgrade head`) run in the app entrypoint, so the schema is always
  current. `app_worker` runs Stockfish from the Debian package built into the
  image (`STOCKFISH_PATH=/usr/games/stockfish`).

Deployment targets:

- **CI/CD**: `.github/workflows/ci.yml` — backend (ruff, mypy, pytest on a
  Postgres service), frontend (lint, typecheck, Vitest, build), Playwright e2e
  against the composed stack, then build + push to GHCR and redeploy via a
  deploy hook on every pushed commit.
- **PaaS**: `render.yaml` blueprint using Render's Free plans (web + PostgreSQL,
  no paid features). Free limits: the service sleeps after 15 idle minutes, the
  database is 1 GB and expires after 30 days. Render has no free worker plan, so
  the blueprint sets `RUN_EMBEDDED_WORKER=1` and the container starts the analysis
  worker alongside the API.
- **AWS**: `infra/cloudformation.yml` provisions one free-tier `t3.micro` EC2
  instance with Docker and starts the whole compose stack; details and free-tier
  guardrails: `infra/README.md`.

E2E tests (Playwright, per feature, in `frontend/e2e/`; GitHub issues tagged
`e2e-test`): with the compose stack running,

```bash
cd frontend
npx playwright install --with-deps chromium   # once
npx playwright test                           # E2E_BASE_URL defaults to http://127.0.0.1:8000
```

SQLite → PostgreSQL migration: the application was written directly for
PostgreSQL (Compose) with Alembic migrations; there are no SQLite-specific code
paths to migrate.

## Deployment assumptions

- One FastAPI process (or several) behind a reverse proxy, PostgreSQL 16, the built
  frontend served as static files from the same origin (`VITE_API_BASE_URL` empty) or
  from an origin listed in `CORS_ORIGINS`.
- Outbound HTTPS to `api.chess.com` is required; set `CHESS_COM_USER_AGENT` with contact
  information. Run `alembic upgrade head` before starting a new version.

## Troubleshooting

- **`Invalid configuration (DATABASE_URL: Field required)`**: copy `.env.example` to `.env`
  or export `DATABASE_URL`.
- **`POSTGRES_PASSWORD` error from `docker compose`**: `.env` is missing; copy `.env.example`.
- **Port 5432 already in use**: set `POSTGRES_PORT` in `.env` and update the port in `DATABASE_URL`.
- **Changed the Postgres password after first start**: the data volume keeps the old password;
  run `docker compose down -v` (this deletes local data) and start again.
- **Database tests are all skipped**: PostgreSQL is not running or not reachable at the
  configured URL; start it with `docker compose up -d db`.
- **`permission denied to create database` in tests**: point `TEST_DATABASE_URL` at a role
  with `CREATEDB`.
- **`alembic check` reports changes**: a model was edited without a migration; generate one.
- **Frontend shows "Backend unavailable"**: start the backend and check `VITE_DEV_PROXY_TARGET`.
