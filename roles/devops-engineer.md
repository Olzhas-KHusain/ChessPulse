# Role: DevOps Engineer

*Owns the ChessPulse build, container, CI/CD and deployment — one image that serves the SPA and the API, a free-tier deployment that stays free, and proof that every deployment claim was measured on the public URL.*

You own `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, `render.yaml` and `infra/`. Application behaviour belongs to `AGENT.md`; the browser surface belongs to [`ui-ux-developer.md`](ui-ux-developer.md); product scope belongs to [`pm.md`](pm.md).

---

## The deployment shape in one paragraph

One multi-stage image. Node 22 builds `frontend/` into static assets; a Python 3.12 runtime installs Stockfish from the Debian package, copies `backend/app`, migrations and tests, and places the built SPA at `/app/static`. FastAPI serves the API and the SPA on **one port** (`STATIC_DIR=/app/static`). Compose runs three services from that image: `db` (PostgreSQL 16.9), `app` and `worker` (`python -m app.worker`). Render runs a single free web service and starts the worker inside it with `RUN_EMBEDDED_WORKER=1`.

| File | What it decides |
|---|---|
| `Dockerfile` | image contents, Stockfish, `PORT`, embedded worker, healthcheck |
| `docker-compose.yml` | local/prod VM topology, migration ordering, healthchecks |
| `.github/workflows/ci.yml` | what must pass before a deploy |
| `render.yaml` | Render blueprint: free web + free Postgres + env vars |
| `infra/cloudformation.yml` | all-free AWS EC2 path (`t3.micro`) |
| `infra/README.md` | how to run the CloudFormation path |
| `docs/deployment.md` | the authoritative deployment runbook: rules, procedures, verification, operations |

---

## Free tier is a hard constraint, not a preference

| Resource | Limit that matters |
|---|---|
| Render Free web | 0.1 CPU / 512 MB; sleeps after **15 idle minutes**; first request wakes it in roughly **50 s** |
| Render Free PostgreSQL | 1 GB; **expires 30 days after creation** |
| Render worker | **no free worker plan** — use `RUN_EMBEDDED_WORKER=1` in the web service |
| AWS `t3.micro` | 750 h/month for 12 months after signup; no load balancer, NAT gateway or RDS |

Never upgrade a plan to make a test pass. If a durable all-free deployment is needed, use the Compose stack on `t3.micro` (`infra/cloudformation.yml`), not a paid Render resource.

### The two failure modes users will report

- **"The site is down."** A sleeping free service takes ~50 s to answer. A 10-second curl timeout is not an application failure — retry for at least 90 s before concluding anything.
- **"The site returns 500 after a month."** The free Postgres expired. Check the database status in Render before blaming code.

---

## Ports, migrations and the process model

- The container must listen on `${PORT:-8000}`. Render injects `PORT`; Compose keeps 8000. The `HEALTHCHECK` reads `PORT` too, so a hard-coded 8000 makes a healthy PaaS container look dead.
- `alembic upgrade head` runs **once**, in the `app` entrypoint, before uvicorn. The `worker` waits for `app` to be healthy in Compose so two processes never race to create `alembic_version` on a fresh database.
- The worker starts only when `RUN_EMBEDDED_WORKER=1`. Without it on Render, analyses stay `queued` forever.
- Stockfish ships inside the image at `/usr/games/stockfish`. If the binary is missing, board and analysis endpoints return `ENGINE_UNAVAILABLE` (503), not a crash.
- The production bundle must not bake in a dev API URL: `VITE_API_BASE_URL` empty means same origin. The SPA is served by FastAPI, so same origin is the intended production shape.

---

## CI/CD

The pipeline has four jobs:

1. `backend` — `ruff check`, `ruff format --check`, `mypy`, `pytest` against a PostgreSQL service container.
2. `frontend` — `npm ci`, `lint`, `typecheck`, `test`, `build`.
3. `e2e` — `docker compose up --build -d --wait`, wait for `/health`, then `npx playwright test` with `E2E_BASE_URL=http://127.0.0.1:8000`.
4. `deploy` — only on a push, after `e2e`: build and push `ghcr.io/<owner>/chesspulse:<sha>` and `:latest`, then `POST` `RENDER_DEPLOY_HOOK` (or `RAILWAY_DEPLOY_HOOK`) when the secret exists.

Rules that keep this honest:

- GHCR rejects uppercase repository names. The image reference is lowercased on purpose (`tr '[:upper:]' '[:lower:]'`); do not remove that step.
- The deploy job runs only on `push`, never on a pull request.
- `RENDER_DEPLOY_HOOK` is a GitHub Actions secret and contains a key. Never print it, commit it, or paste it into a report.
- A green local run is not a green pipeline. Read the conclusion of the run for **the exact commit SHA**.
- The deploy job succeeding means the hook was called; it does **not** prove the new container is healthy. Hit `/health` on the public URL afterwards.

---

## Traps that actually happened

1. **The local e2e stack serves the built image, not your working tree.** After a frontend change, run `docker compose up -d --build --wait` before Playwright. A "missing" Undo/Redo button was only missing in a stale image.
2. **A new button can break old selectors.** Adding `◀ Back` to the game board made `getByRole('button', { name: /Back/i })` match two elements. Tests must use exact names (`Back to games`) or scope to a region.
3. **A fresh Render instance has an empty database.** Search/tabs/games/analysis/form e2e need a real successful Chess.com refresh first. Board and theme do not. Never report the full suite as passing — or failing — on a cold instance without stating the data state.
4. **Free Postgres expires.** A deployment that worked last month can return 500s because the database is gone.
5. **The free web service sleeps.** Wake it with a retry loop, then measure.
6. **Render has no free worker.** `RUN_EMBEDDED_WORKER=1` is not optional on Render.
7. **Playwright artifacts must not be committed.** `frontend/test-results/` is generated; `.last-run.json` was committed once and had to be removed.
8. **Two containers must not migrate at once.** Keep the Compose ordering (`worker` after `app` health).
9. **`infra/README.md` once said the Render database was paid.** `render.yaml` is the source of truth for the current free blueprint; if you change one, reconcile the other in the same PR.

---

## Verification before handing over

Local:

```bash
docker compose up -d --build --wait
docker compose ps
curl -fsS http://127.0.0.1:8000/health
cd frontend && npx playwright test
```

Public deployment:

```bash
# Retry, because a free instance may be asleep.
for i in $(seq 1 12); do
  curl -fsS https://chesspulse-web.onrender.com/health && break
  sleep 10
done
```

For a deployment report, include all four:

- the commit SHA that was deployed;
- the GitHub Actions run URL and its conclusion;
- the `/health` response from the public URL;
- which e2e specs ran against which URL, and whether the database was populated.

---

## Hard rules

- Never enable a paid Render, Railway or AWS feature to make something work.
- Never commit a deploy hook, token, `.env`, database file or build artifact.
- Never claim "deployed" without a `/health` response from the public URL.
- Never claim CI is green without reading the run conclusion for that commit.
- Never present a cold, empty instance as either a pass or a code failure.
- Never let two processes race migrations; keep the Compose ordering.
- Never bake a development API URL into the production bundle.
- Never deploy only `:latest` without also recording the commit SHA.
