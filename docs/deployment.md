# Deployment runbook

This is the authoritative operational document for building, shipping and running
ChessPulse. It covers the local production-shaped stack, Render Free, the all-free
AWS path, CI/CD, migrations, verification and the incidents that actually happen.

Companion documents:

- [`README.md`](../README.md) — product overview and local development.
- [`infra/README.md`](../infra/README.md) — CloudFormation specifics.
- [`roles/devops-engineer.md`](../roles/devops-engineer.md) — ownership and hard rules.
- [`docs/release/RELEASE_CHECKLIST.md`](release/RELEASE_CHECKLIST.md) — checks executed
  for a specific release.
- [`docs/KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) — what the product does not do.

When this document and a script disagree, the script is the truth. Fix the document in
the same pull request.

---

## 1. Rules

These are not recommendations. A deployment that breaks one of them is not finished,
even if the site happens to respond.

1. **Free tier only.** Do not enable a paid Render, Railway, AWS or GCP resource to make
   a check pass. If the free tier cannot support the requirement, say so and use another
   free path (`infra/cloudformation.yml`), not a paid one.
2. **No secrets in the repository, an issue, a chat message or a log.** That includes
   `RENDER_DEPLOY_HOOK`, database URLs with passwords, `.env`, tokens and dumps.
3. **Evidence, not adjectives.** "Deployed" means: the commit SHA, the CI run conclusion
   for that SHA, a `/health` response from the public URL and one database-backed
   request. `/health` alone is not proof of a working database or a working deployment.
4. **Do not deploy a red build.** The deploy job must not be triggered manually to bypass
   backend, frontend or e2e failures.
5. **One migration runner.** `alembic upgrade head` runs once, in the `app` container
   entrypoint. The worker must not migrate. In Compose it waits for `app` to be healthy.
6. **Migrations are forward-only in production.** Do not run `alembic downgrade` against
   a live database. Ship expand → migrate → contract changes across releases.
7. **The database is never publicly exposed.** Compose binds PostgreSQL to `127.0.0.1`;
   Render's database is internal. Do not publish `5432` to `0.0.0.0`.
8. **The production bundle has no development URL.** `VITE_API_BASE_URL` must be empty in
   the image build; the SPA is served by FastAPI on the same origin.
9. **A cold, empty instance is neither a pass nor a failure.** Free instances sleep, and
   a fresh database needs a successful Chess.com refresh. State the data state whenever
   you report e2e results.
10. **Destructive commands need explicit approval.** `docker compose down -v`, deleting
    a Render database, replacing a volume and `DROP`/`TRUNCATE` destroy data. Take a dump
    first and say what will be lost.
11. **Do not commit build artifacts.** `frontend/dist/`, `frontend/test-results/`,
    `node_modules/`, `.env` and dumps stay out of git.
12. **Change the deployment shape in one PR.** If you change the Dockerfile, Compose,
    CI, `render.yaml` or the AWS template, update this runbook and the DevOps role in
    the same pull request.

---

## 2. What gets deployed

One multi-stage image serves both the UI and the API.

| Stage | Base | What it does |
|---|---|---|
| `frontend` | `node:22-bookworm-slim` | `npm ci`, `npm run build`; the Vite output is copied into the runtime image |
| `runtime` | `python:3.12-slim` | installs Stockfish from Debian, `pip install .`, copies `app/`, `migrations/`, `tests/`, and the built SPA to `/app/static` |

Runtime facts:

- FastAPI listens on `${PORT:-8000}`. Render injects `PORT`; Compose uses `8000`.
- `STATIC_DIR=/app/static` makes FastAPI serve the built SPA and the API from one origin.
- `alembic upgrade head` runs before uvicorn in the container command.
- `RUN_EMBEDDED_WORKER=1` starts `python -m app.worker` in the same container, in the
  background. Without it, analysis jobs stay `queued`.
- Stockfish is at `/usr/games/stockfish`. A missing binary produces a `503`
  `ENGINE_UNAVAILABLE`, not a crash.
- The Docker `HEALTHCHECK` calls `/health` on `$PORT`.

Topologies:

```
Compose (local / AWS EC2)          Render Free
┌──────────┐                       ┌─────────────────────────────┐
│   db     │  postgres:16.9        │  web service (Dockerfile)   │
│  :5432   │  (127.0.0.1 only)     │  uvicorn + embedded worker  │
└────┬─────┘                       │  Stockfish (Debian)         │
     │                             └──────────────┬──────────────┘
┌────┴─────┐   ┌──────────┐                      │
│   app    │   │  worker  │                      │ connectionString
│ :8000    │   │ stockfish│                      ▼
└──────────┘   └──────────┘               ┌──────────────┐
                                          │ free Postgres│
                                          │ 1 GB, 30 days│
                                          └──────────────┘
```

The `worker` service uses the same image as `app`; it does not rebuild it.

---

## 3. Environments

| Environment | URL | Database | Worker | Persistence | Notes |
|---|---|---|---|---|---|
| Local dev | `http://localhost:5173` | Compose `db` | manual `python -m app.worker` | volume | Vite proxies `/api` and `/health` to `:8000` |
| Local production-shaped | `http://127.0.0.1:8000` | Compose `db` | Compose `worker` | volume | The exact image used in production |
| CI e2e | `http://127.0.0.1:8000` | CI service + Compose | Compose `worker` | ephemeral | Live Chess.com data; not hermetic |
| Render Free | `https://chesspulse-web.onrender.com` | Render free Postgres | embedded | Render disk | Sleeps after 15 idle minutes; DB expires after 30 days |
| AWS free tier | `http://<PublicIp>:8000` | Compose `db` on the instance | Compose `worker` | EBS volume | 750 h/month `t3.micro` for 12 months |

Render is the current public deployment. AWS is the durable all-free alternative. They
are not active-active: pick one as the public entry point.

---

## 4. Local production-shaped stack

Use this before every merge that touches runtime behaviour. It exercises the same image
that Render builds.

### 4.1 Configure

```bash
cp .env.example .env
# Edit .env:
#   POSTGRES_PASSWORD=<a real local password>
#   Keep DATABASE_URL consistent if you use it outside Compose.
```

`docker compose` reads `POSTGRES_PASSWORD` and builds `DATABASE_URL` for `app` and
`worker` itself. `.env` is git-ignored; never commit it.

### 4.2 Start and verify

```bash
docker compose up -d --build --wait
docker compose ps
curl -fsS http://127.0.0.1:8000/health
curl -fsS "http://127.0.0.1:8000/api/v1/players/olzhaswlk/overview?time_class=rapid&days=30"
```

Expected `/health`:

```json
{"status":"ok","service":"chesspulse-backend","version":"0.1.0","environment":"production"}
```

The player request proves PostgreSQL and the ingestion path work. On a fresh database it
calls Chess.com and can take longer than `/health`; a `502`/`504` here is an upstream
problem, not proof that the container is broken.

### 4.3 E2E against the built image

```bash
cd frontend
npx playwright install --with-deps chromium   # once
npx playwright test
```

`E2E_BASE_URL` defaults to `http://127.0.0.1:8000`. The suite is **not hermetic**: search,
tabs, games, analysis and form specs need a populated database and a reachable Chess.com.
Board and theme specs do not. Never report the full suite as green on an empty database.

After a frontend change, rebuild before running Playwright. A stale image will make a
new button look absent.

### 4.4 Stop

```bash
docker compose down        # keeps the database volume
docker compose down -v     # DELETES the local database — explicit approval required
```

---

## 5. Configuration

### 5.1 Build time vs runtime

| Variable | When it is read | Where it matters |
|---|---|---|
| `VITE_API_BASE_URL` | **build time** (`npm run build`) | Must be empty for the single-origin image. Changing it requires rebuilding the image. |
| `VITE_DEV_PROXY_TARGET` | dev server only | Local Vite proxy; not in the production bundle. |
| `PORT` | runtime | Container listen port. Render injects it; Compose defaults to `8000`. |
| All backend variables | runtime, at startup | Settings are validated once; invalid values stop the process with a configuration error. |

Never put a secret in a `VITE_*` variable. Vite inlines those values into JavaScript
that every visitor downloads.

### 5.2 Backend variables

Full list with defaults: [`.env.example`](../.env.example). The ones that cause outages:

| Variable | Required | Default | Notes |
|---|---|---|---|
| `DATABASE_URL` | **yes** | — | `postgresql://` or `postgresql+psycopg://`; must include a database name. Render's `connectionString` property works unchanged with the pinned psycopg 3 driver. |
| `APP_ENV` | no | `development` | `development`, `test` or `production`. Compose and Render set `production`. |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`…`CRITICAL`. Do not use `DEBUG` in production. |
| `CORS_ORIGINS` | no | `http://localhost:5173` | Comma-separated. Only needed when the UI is on a different origin; the image is same-origin. |
| `CHESS_COM_USER_AGENT` | strongly recommended | `ChessPulse/0.1.0` | Chess.com asks for a recognizable value with contact information. |
| `STATIC_DIR` | image sets it | empty | Empty means API-only. The image sets `/app/static`. |
| `RUN_EMBEDDED_WORKER` | Render only | unset | `1` starts the analysis worker in the web container. |
| `STOCKFISH_PATH` | image sets it | empty | Empty means search `PATH`. The image sets `/usr/games/stockfish`. |
| `DATASET_WINDOW_DAYS` | no | `90` | Days of all time classes stored per refresh (30–730). Larger = more Chess.com requests. |
| `CACHE_TTL_SECONDS` | no | `43200` | 12 h; Chess.com refreshes at most every 12 h. |
| `ANALYSIS_DEPTH` / `ANALYSIS_THREADS` / `ANALYSIS_HASH_MB` | no | `12` / `1` / `64` | Part of the analysis cache key. Changing them does not invalidate old rows but prevents reuse. |

Database URL rules:

- The password must be URL-encoded if it contains `@`, `:`, `/`, `?`, `#` or `%`.
- `postgresql://` is accepted; with the pinned dependencies SQLAlchemy resolves it to the
  psycopg 3 driver (verified with `create_engine`). `postgresql+psycopg://` is the
  explicit form used by Compose.
- If you connect to a Render database from outside Render, use its **external** URL and
  keep the TLS parameters Render provides.

### 5.3 Secrets

| Secret | Where it lives | Who can see it |
|---|---|---|
| `POSTGRES_PASSWORD` | local `.env`; Render injects the database URL | local machine / Render |
| `DATABASE_URL` | Render environment; Compose constructs it | Render / container |
| `RENDER_DEPLOY_HOOK` | GitHub Actions secret | GitHub Actions |
| `E2E_USERNAME` (optional) | GitHub Actions secret | GitHub Actions |
| `GITHUB_TOKEN` | provided by Actions | Actions only |

Rules:

- Add Actions secrets through the GitHub UI (Settings → Secrets and variables → Actions).
  Do not print a secret to verify it; verify by using it.
- Rotating the database password is a coordinated change: update the database role,
  update every consumer, restart `app` and `worker`.
- The settings validator names invalid variables but never echoes their values. Do not
  add logging that prints `DATABASE_URL`.

### 5.4 Render database compatibility

`render.yaml` maps `DATABASE_URL` from the database's `connectionString` property. No
manual rewrite is needed. Do not override `DATABASE_URL` in the dashboard with a
hand-copied URL unless you are deliberately pointing at another database; a stale copy
survives blueprint syncs and causes confusing failures.

---

## 6. CI/CD

Workflow: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).

### 6.1 Jobs

| Job | Trigger | What must pass |
|---|---|---|
| `backend` | push + PR | `ruff check`, `ruff format --check`, `mypy`, `pytest` against a PostgreSQL 16 service |
| `frontend` | push + PR | `npm ci`, `lint`, `typecheck`, `test`, `build` |
| `e2e` | push + PR, after backend + frontend | Compose stack builds and becomes healthy, then Playwright runs against `http://127.0.0.1:8000` |
| `deploy` | **push only**, after e2e | build and push `ghcr.io/<owner>/chesspulse:<sha>` and `:latest`, then call the deploy hook if configured |

Pull requests never deploy. A failing `e2e` blocks `deploy`.

### 6.2 What the deploy job does and does not do

- It pushes a portable image to GHCR. **Render does not run that image.** `render.yaml`
  uses `runtime: docker` and builds from the repository `Dockerfile`. GHCR is an
  artifact and a rollback source for hosts that pull images.
- If `RENDER_DEPLOY_HOOK` (or `RAILWAY_DEPLOY_HOOK`) exists, it `POST`s the hook. The
  hook asks the platform to build the current commit.
- A successful hook call means "the platform accepted the request". It does **not** mean
  the new container is healthy. Verify the public URL afterwards.

### 6.3 Duplicate deploys

`render.yaml` currently sets `autoDeploy: true`, and CI can also call the deploy hook.
On a push to the connected branch, Render may start a build on its own and CI may start
another after e2e. This is redundant, not harmful, but it wastes free build minutes.

Choose one:

- **Recommended:** set `autoDeploy: false` in `render.yaml` and keep the hook, so a
  deployment happens only after all tests pass.
- Or remove the `RENDER_DEPLOY_HOOK` secret and let Render's auto-deploy own the flow.
  In that case CI does not gate the deployment.

Do not leave both enabled and then claim CI gates production.

### 6.4 How to read a run

1. Open the Actions run for the **exact commit SHA** you intend to deploy. A green run on
   a different SHA proves nothing.
2. Confirm all four jobs for a `main` push: `backend`, `frontend`, `e2e`, `deploy`.
3. If `e2e` failed, download the `playwright-traces` artifact before retrying.
4. If `deploy` failed, read whether the failure was the GHCR push or the hook. A failing
   hook is not a code failure.
5. Record the run URL in the deployment report.

Optional, if the GitHub CLI is installed:

```bash
gh run list --branch main --limit 5
gh run view <run-id> --log-failed
```

### 6.5 Concurrency

The workflow cancels an in-progress run for the same ref when a new commit arrives. If
you need the result for an older SHA, read the old run; it may be cancelled by design.

---

## 7. Release procedure

Follow the order. Do not skip step 5.

1. **Scope the change.** Link the issue/PR and state whether it changes the schema,
   runtime configuration, the image or only the UI.
2. **Run the local checks** that match the change (section 9).
3. **Open a PR.** CI must be green; `deploy` is skipped on PRs by design.
4. **Merge to `main`.** The push triggers backend, frontend, e2e and (if green) deploy.
5. **Confirm the deployed commit.** In Render, open the service → Events/Deploys and check
   the commit SHA. Do not infer the SHA from `/health`; it returns the application
   version, not the commit.
6. **Run post-deploy verification** (section 8).
7. **Record evidence**: SHA, run URL, `/health`, database-backed response, public URL.
8. If verification fails, **roll back or fix forward** (section 7.2) and say which.

### 7.1 Migrations

The container runs `alembic upgrade head` before uvicorn. Consequences:

- A broken migration prevents the container from starting; the platform health check
  fails and the previous version may keep serving or be replaced by a failing one,
  depending on the platform.
- On Compose, the worker waits for `app` health, so two processes never race to create
  `alembic_version`.
- The current head in this repository is `0004`. Check before release:

```bash
cd backend
.venv/Scripts/python.exe -m alembic current   # Windows
alembic current                               # Linux/macOS
```

Migration rules:

- Never edit a migration that has already run in an environment. Add a new revision.
- Additive first: add nullable columns/tables, deploy code that tolerates both shapes,
  backfill, then make columns required and remove old ones in a later release.
- Test the migration against a copy or a fresh database, not only against the dev DB.
- Run `alembic check` to catch model/migration drift:

```bash
cd backend
.venv/Scripts/python.exe -m alembic check
```

- Before a destructive migration on a hosted database, take a dump (section 10.4) and
  confirm it restores. The free plans do not guarantee managed backups.

### 7.2 Rollback

| Situation | Action |
|---|---|
| Bad frontend/backend code, schema compatible | Redeploy the previous known-good commit SHA from the Render dashboard (or re-run its CI deploy). Verify again. |
| Broken migration, schema not yet destructive | Fix forward with a new migration; do not `downgrade` a live database. If the old code cannot run on the new schema, restore the dump into a new database and point `DATABASE_URL` at it. |
| Database expired / deleted | Recreate the free database, point `DATABASE_URL` at it, redeploy; data is lost unless you have a dump. |
| Provider (Chess.com) outage | Do not redeploy. The app returns `502`/`504`/`UPSTREAM_*`; cached data may still serve with `data_status`. |

A rollback is not complete until the public URL passes section 8 again.

---

## 8. Post-deploy verification

Run these against the public URL. For a sleeping free instance, allow at least 90 seconds.

### 8.1 Liveness

```bash
for i in $(seq 1 12); do
  curl -fsS --max-time 10 https://chesspulse-web.onrender.com/health && break
  sleep 10
done
```

Expected: `{"status":"ok",...}`. This endpoint does **not** query PostgreSQL; it only
proves the process is up.

### 8.2 Database + ingestion

```bash
curl -fsS --max-time 120 \
  "https://chesspulse-web.onrender.com/api/v1/players/olzhaswlk/overview?time_class=rapid&days=30"
```

Check that the response contains `games_count`, `data_status` and a rating. On a fresh
database this triggers a Chess.com refresh. A `502`/`504` here is an upstream or timeout
problem; a `500` usually means the schema or database is broken.

### 8.3 Engine

```bash
curl -fsS --max-time 120 -X POST \
  https://chesspulse-web.onrender.com/api/v1/board/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"fen":"rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"}'
```

Check `best_move_uci` and `engine.name` / `engine.version`. A `503`
`ENGINE_UNAVAILABLE` means Stockfish is missing or not executable in the image.

### 8.4 SPA

```bash
curl -fsS https://chesspulse-web.onrender.com/ | grep -q 'id="root"'
```

This proves the static build is mounted and the catch-all route serves `index.html`.

### 8.5 Report template

```text
Deployed: <commit SHA>
CI run:   <URL> — <conclusion>
URL:      <public URL>
/health:  <response>
DB check: <endpoint> — <status, key fields>
Engine:   <name version, depth, best move>  (if changed)
E2E:      <specs run, base URL, database populated: yes/no>
Caveats:  <sleep/expiry/upstream, or "none">
```

Do not write "all tests pass" without naming what ran and where.

---

## 9. Local checks before a PR

Run what the change touches. The full gate:

```bash
# Backend (from backend/)
.venv/Scripts/python.exe -m ruff check app tests migrations
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m mypy .
.venv/Scripts/python.exe -m pytest -q

# Frontend (from frontend/)
npm run lint
npm run typecheck
npm run format:check
npm test
npm run build
```

Linux/macOS replaces `.venv/Scripts/python.exe` with `.venv/bin/python`.

Database tests need a reachable PostgreSQL with `CREATEDB`; without it they skip. A run
with skipped database tests is not a full backend run — say so.

The Vite build emits a chunk-size warning for the single large bundle. It is a warning,
not a failure. Do not "fix" it by adding a code-splitting change to an unrelated PR.

---

## 10. Operations

### 10.1 Logs

```bash
docker compose logs -f --tail=200 app worker
docker compose ps
```

On Render: service → Logs. The platform log stream includes the entrypoint
(`alembic upgrade head`, uvicorn) and the embedded worker. If the worker is silent,
first confirm `RUN_EMBEDDED_WORKER=1`.

### 10.2 Restart

```bash
docker compose restart app worker
```

On Render: Manual Deploy → Restart service, or redeploy the same commit. A restart does
not run new migrations beyond the entrypoint's `alembic upgrade head`.

### 10.3 Database shell

```bash
docker compose exec db psql -U chesspulse -d chesspulse
```

Read-only queries are safe. Anything that writes needs a dump and explicit approval.

### 10.4 Backup and restore

```bash
# Backup (custom format)
docker compose exec -T db pg_dump -U chesspulse -d chesspulse -Fc > chesspulse.dump

# Restore into an empty database
docker compose exec -T db pg_restore -U chesspulse -d chesspulse --clean --if-exists < chesspulse.dump
```

For Render, use the external connection string and a local `pg_dump`/`pg_restore` of the
same major version. Treat the URL as a secret: do not paste it into a shell that records
history on a shared machine, and do not commit the dump.

The Render free plan is not a backup service. Expiry and deletion are real data-loss
events.

### 10.5 Free-tier lifecycle

**The service is asleep, not down.** Render Free spins down after 15 idle minutes and
takes roughly 50 seconds to wake. Retry for at least 90 seconds before escalating.

**The database expires after 30 days.** The free PostgreSQL instance is 1 GB and expires
30 days after creation. Before expiry:

1. Take a dump (10.4).
2. Recreate the database from the blueprint, or create a new free database and update
   `DATABASE_URL`.
3. Redeploy, restore if needed, then verify section 8.

A `500` that appears "after a month" is usually an expired database, not a code
regression.

**Resource limits.** Free web: 0.1 CPU / 512 MB. Keep `ANALYSIS_THREADS=1` and avoid
parallel analysis requests; Stockfish is CPU-bound and the free instance has very little
CPU. If analysis latency is unacceptable, that is a capacity decision, not a reason to
upgrade silently.

### 10.6 Analysis queue

- Jobs are claimed by `python -m app.worker`; on Render it runs inside the web container.
- `ANALYSIS_JOBS` stuck in `queued`: check `RUN_EMBEDDED_WORKER`, worker logs and database
  connectivity.
- A job left `running` longer than `ANALYSIS_STALE_JOB_MINUTES` (30 by default) is
  recovered as stale.
- A repeatedly failing job becomes `failed` after `ANALYSIS_JOB_MAX_ATTEMPTS` (3) and
  stays failed until re-requested.
- Changing `ANALYSIS_DEPTH`, `ANALYSIS_THREADS` or `ANALYSIS_HASH_MB` changes
  `profile_hash`; old analyses remain but are not reused.

### 10.7 Provider behaviour

- Data is cached for `CACHE_TTL_SECONDS` (12 h by default).
- After a failed refresh, the app waits `REFRESH_FAILURE_COOLDOWN_SECONDS` (or the
  provider's `Retry-After`, if longer) before retrying.
- `UPSTREAM_RATE_LIMITED`, timeouts and `5xx` from Chess.com surface as gateway errors;
  they are not fixed by redeploying ChessPulse.
- `CHESS_COM_USER_AGENT` should identify the deployment and include contact information.
  Do not impersonate a browser.

---

## 11. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| First request takes ~50 s | Free web service was asleep | Wait/retry; this is expected. Do not redeploy. |
| `/health` is 200 but data endpoints fail | Database missing, expired or unreachable | Check the database status; run the DB-backed request in 8.2; inspect logs. |
| `500` after weeks of uptime | Free PostgreSQL expired | Export/recreate as in 10.5. |
| `502` / `504` on player endpoints | Chess.com timeout or outage | Retry, check provider status, inspect `UPSTREAM_*` logs. Do not redeploy. |
| `503 ENGINE_UNAVAILABLE` | Stockfish missing/not executable | Check `STOCKFISH_PATH` and the image; rebuild. |
| Analyses stay `queued` | `RUN_EMBEDDED_WORKER` unset on Render, or worker down | Set it to `1`, restart, inspect worker logs. |
| Container exits at boot with a config error | Missing `DATABASE_URL`, wrong scheme, missing DB name | Read the error; it names the variable without printing the value. |
| `POSTGRES_PASSWORD` error from Compose | `.env` missing | Copy `.env.example` to `.env` and set the password. |
| Port 5432 already in use | Local PostgreSQL running | Set `POSTGRES_PORT` and keep `DATABASE_URL` consistent. |
| Changed the database password, auth fails | Volume still has the old role password | Update the role, or recreate the volume (data loss). |
| `alembic check` reports changes | Model changed without a migration | Generate a revision and review it. |
| Playwright cannot find a new control | Stale image | `docker compose up -d --build --wait`, then rerun. |
| Playwright passes locally, fails in CI | Different data state or live provider | Read the trace; state the DB state; do not call it flaky without evidence. |
| Render deploys twice per push | `autoDeploy: true` plus CI hook | Choose one flow (6.3). |
| Site works over HTTP on EC2 but not HTTPS | No TLS terminator in the template | Put a TLS reverse proxy in front, or use the Render path. |

---

## 12. Security

- **No application authentication.** The app exposes public Chess.com analytics and an
  engine endpoint. Do not put private data in the database or assume requests are
  trusted.
- **No inbound rate limiting.** The backend limits outbound provider retries, not inbound
  traffic. An exposed instance can be used to burn CPU with board analysis. Keep the
  deployment small, monitor it, and do not advertise an unbounded public endpoint.
- **Database isolation.** Compose publishes PostgreSQL only on `127.0.0.1`. Do not change
  that to `0.0.0.0` for convenience. On Render, use the internal connection string for
  the service.
- **TLS.** Render terminates TLS for `*.onrender.com`. The CloudFormation template serves
  plain HTTP on `:8000`; add a reverse proxy with a certificate before handling anything
  sensitive.
- **AWS exposure.** The template opens SSH (22) and the app (8000) to `0.0.0.0/0`.
  Restrict SSH to your own address in the security group and do not leave the instance
  running unused. `t3.micro` is free for 12 months, not forever.
- **Secrets.** The configuration layer validates `DATABASE_URL` with SQLAlchemy and
  reports invalid variables without echoing values. Keep it that way; never log full
  connection strings.
- **Dependencies.** CI runs the pinned installs. Dependabot/upgrades are separate changes;
  run the full gate after any dependency bump.
- **Images.** The runtime image runs as root by default in this Dockerfile. Do not add
  untrusted build steps; if you change the base image or add packages, review the
  resulting attack surface in the same PR.

---

## 13. Render Free runbook

Current blueprint: [`render.yaml`](../render.yaml). The existing public service is
`chesspulse-web`; the database is `chesspulse-db`.

### 13.1 First-time / recreation

1. Render Dashboard → **New** → **Blueprint** → connect the GitHub repository.
2. Render detects `render.yaml`. Confirm both resources use the **Free** plan.
3. Apply. The web service builds `./Dockerfile`; the database is created and its
   `connectionString` is injected as `DATABASE_URL`.
4. Wait for the first deploy. The entrypoint runs migrations, then uvicorn; with
   `RUN_EMBEDDED_WORKER=1` the worker starts too.
5. Add the deploy hook to GitHub Actions if you want CI-gated deploys:
   Render service → Settings → Deploy Hook → copy; GitHub repository → Settings →
   Secrets and variables → Actions → New repository secret `RENDER_DEPLOY_HOOK`.
   Never paste the value into an issue, a document or a chat.
6. Verify section 8.

### 13.2 Changing configuration

- Blueprint-managed variables: edit `render.yaml`, commit, let the blueprint sync. Manual
  dashboard edits to managed variables can be overwritten.
- Secrets that must not live in the repository: set them in the Render dashboard.
- After changing `PORT`, `STATIC_DIR` or `RUN_EMBEDDED_WORKER`, redeploy and verify; these
  are runtime, not build-time.

### 13.3 Known limitations

- No free background worker; the embedded worker shares 0.1 CPU with the API.
- The service sleeps, so the first request is slow and scheduled work does not run while
  asleep.
- The free database expires; there is no always-free Render database.
- Render builds from the Dockerfile, not from GHCR. The image tag in CI is not what Render
  runs.
- The free instance is not a production SLA. Use the AWS path when durability matters.

---

## 14. AWS free-tier runbook

Template: [`infra/cloudformation.yml`](../infra/cloudformation.yml). Details:
[`infra/README.md`](../infra/README.md).

### 14.1 Prerequisites

- An AWS account with a verified payment method (phone verification is required even for
  free tier).
- AWS CLI configured (`aws sts get-caller-identity`).
- An existing EC2 key pair in the target region.
- A region where `t3.micro` is free-tier eligible; otherwise use `t2.micro` and confirm
  the AMI.

### 14.2 Deploy

```bash
aws cloudformation deploy \
  --template-file infra/cloudformation.yml \
  --stack-name chesspulse \
  --parameter-overrides KeyName=<your-key-pair> \
  --capabilities CAPABILITY_IAM
```

If the default AMI is not valid in your region, pass `AmiId=<amazon-linux-2023-ami>`.

The instance installs Docker, clones the repository, writes `/opt/chesspulse/.env`, and
runs `docker compose up -d --build --wait`. It serves `http://<PublicIp>:8000`.

### 14.3 First-boot security fix

The template's user data contains `POSTGRES_PASSWORD=change-me-before-production`. That
value initializes the database, so changing only `.env` later does not change the role
password.

Before exposing the instance:

1. Restrict the security group's SSH ingress to your IP.
2. SSH in and change the password safely (interactive `psql`, not a command line that
   leaks into shell history):

```bash
cd /opt/chesspulse
sudo nano .env                 # set a strong POSTGRES_PASSWORD
docker compose exec db psql -U chesspulse -d chesspulse
# ALTER USER chesspulse WITH PASSWORD '<same strong password>';
# \q
docker compose up -d --force-recreate app worker
```

3. Verify `/health` and a database-backed request from the public IP.
4. If the old password was ever exposed, treat the database as compromised and recreate
   it after taking a dump.

### 14.4 Update

```bash
ssh ec2-user@<PublicIp>
cd /opt/chesspulse
git pull
docker compose up -d --build --wait
```

The app entrypoint runs new migrations. The worker waits for app health.

### 14.5 Free-tier guardrails

- One `t3.micro` instance, 750 h/month for 12 months after signup.
- 30 GB gp3 root volume.
- No load balancer, NAT gateway, RDS or paid add-ons.
- CloudFormation stack deletion removes the instance and its volume
  (`DeleteOnTermination: true`). Export data first.
- The instance is a single point of failure. There is no HA and no managed backup.

---

## 15. Change checklist

Use this when you touch deployment-related files.

| If you change… | Also update / check |
|---|---|
| `Dockerfile` | `docker compose up --build`, Render build, `/health`, board engine check |
| `docker-compose.yml` | local stack, CI e2e, worker ordering, volumes |
| `.github/workflows/ci.yml` | required checks, deploy gate, secrets documented here |
| `render.yaml` | this runbook, `infra/README.md`, `roles/devops-engineer.md`; confirm no paid plan |
| `infra/cloudformation.yml` | `infra/README.md`, this runbook, free-tier resources |
| `.env.example` / settings | configuration table in section 5, Compose/Render env |
| A migration | `alembic check`, fresh-database upgrade, release order in 7.1 |
| The public URL | README, role doc, this runbook, verification commands |

---

## 16. Quick reference

```bash
# Local stack
docker compose up -d --build --wait
curl -fsS http://127.0.0.1:8000/health
docker compose logs -f --tail=200 app worker
docker compose down          # keep data
docker compose down -v       # DESTROYS data

# Migrations
cd backend
alembic current
alembic upgrade head
alembic check

# Full local gate
.venv/Scripts/python.exe -m ruff check app tests migrations
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m mypy .
.venv/Scripts/python.exe -m pytest -q
cd ../frontend
npm run lint && npm run typecheck && npm run format:check && npm test && npm run build
npx playwright test

# Public verification
curl -fsS --max-time 10 https://chesspulse-web.onrender.com/health
curl -fsS --max-time 120 "https://chesspulse-web.onrender.com/api/v1/players/olzhaswlk/overview?time_class=rapid&days=30"
curl -fsS https://chesspulse-web.onrender.com/ | grep -q 'id="root"'
```
