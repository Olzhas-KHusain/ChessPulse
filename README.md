# ChessPulse

Web application for analyzing a Chess.com player's Rapid games from the last rolling
30 days. This repository currently contains the **development environment, application
skeleton, database schema, Chess.com provider adapter, ingestion, cache policy, and the
player endpoints** `GET /api/v1/players/{username}/overview`, `/rating-history`,
`/openings`, `/opponents`, `/games` and `/games/{game_id}`, and the **React dashboard**
(search, overview, rating chart, openings, opponents, paginated games, game details).

Engineering rules: `AGENT.md`. Workflow: `process.md`. Product and technical
specification: `spec.md`. Feature specifications: `docs/specs/` (database schema,
Chess.com provider, ingestion, cache policy, overview, breakdown and games APIs, frontend dashboard). Architecture decisions: `docs/adr/`.

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
docker-compose.yml   Local PostgreSQL only
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
alembic upgrade head         # creates/updates the schema (revisions 0001–0003)
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
```

The worker claims jobs with `FOR UPDATE SKIP LOCKED`, so several workers can run in
parallel without sharing a game. Results are cached per `(game, profile)`, where the
profile is the configured depth, thread count and hash size.

Endpoints:

- `POST /api/v1/players/{username}/games/{game_id}/analysis` — request (idempotent;
  returns the cached result when it already exists).
- `GET  /api/v1/players/{username}/games/{game_id}/analysis` — current state
  (`missing`, `queued`, `running`, `completed`, `failed`) and the payload when done.

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
| `STOCKFISH_PATH`                 | no       | Stockfish executable; empty = search `PATH`                    |
| `ANALYSIS_DEPTH`                 | no       | Fixed search depth, `12` by default (6–30)                     |
| `ANALYSIS_THREADS` / `ANALYSIS_HASH_MB` | no | Engine threads (`1`) and hash size (`64`)                    |
| `ANALYSIS_JOB_MAX_ATTEMPTS`      | no       | Claims before a failing job stays failed, `3` by default       |
| `POSTGRES_USER/PASSWORD/DB/PORT` | compose  | Used by `docker-compose.yml`; keep in sync with `DATABASE_URL` |
| `VITE_DEV_PROXY_TARGET`          | no       | Backend URL for the Vite dev proxy                             |
| `VITE_API_BASE_URL`              | no       | API base URL for built bundles (empty = same origin)           |

The values in `.env.example` are local-development placeholders, not real credentials.

## Database schema and migrations (Alembic)

The schema has seven tables: `players`, `games`, `player_games`, `openings`,
`cache_metadata`, `analysis_jobs`, `game_analysis`. Keys, constraints, deletion rules, UTC
handling, and the differences from `spec.md` are documented in
`docs/specs/database-schema.md`.

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
- Engine-based metrics (accuracy, blunders, estimated Elo) are **not** part of the MVP.

## Deployment assumptions

- One FastAPI process (or several) behind a reverse proxy, PostgreSQL 16, the built
  frontend served as static files from the same origin (`VITE_API_BASE_URL` empty) or
  from an origin listed in `CORS_ORIGINS`.
- Outbound HTTPS to `api.chess.com` is required; set `CHESS_COM_USER_AGENT` with contact
  information. Run `alembic upgrade head` before starting a new version.
- Docker Compose in this repository is for local PostgreSQL only; a production
  deployment target has not been chosen (spec §20).

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
