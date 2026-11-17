# Observability and environments

This document explains the development/production split, the OpenTelemetry
pipeline, the application metrics, the dashboard, the alert rules and the AI
on-call responder. [`docs/deployment.md`](deployment.md) remains the
authoritative deploy runbook; when a command here and a script disagree, the
script wins — fix the document in the same pull request.

Everything described here runs on free or self-hosted components. No paid
Render, Grafana, AWS or Datadog feature is required.

---

## 1. Environments

Two environments exist, and they never share a database, credentials or a
Compose project:

| | Development | Production |
|---|---|---|
| Compose trigger | `docker compose --env-file .env.development ...` | `docker compose --env-file .env.production ...` |
| Project name | `chesspulse-dev` | `chesspulse-prod` |
| PostgreSQL volume | `chesspulse-dev_pgdata` | `chesspulse-prod_pgdata` |
| Host DB port | `5432` | `5433` |
| `APP_ENV` | `development` (`/docs` enabled) | `production` (`/docs` disabled) |
| OTel | enabled, collector on the host | disabled until a collector is configured |
| Public entry point | `http://127.0.0.1:8000` | Render `https://chesspulse-web.onrender.com` |

Templates: [`.env.development.example`](../.env.development.example) and
[`.env.production.example`](../.env.production.example). The real
`.env.development` / `.env.production` files are git-ignored.

The Compose project name is what isolates the stacks. Because the volume is
declared as `pgdata`, Compose prefixes it with the project name automatically —
there is no shared `chesspulse_pgdata` between environments.

### 1.1 Start development

```bash
cp .env.development.example .env.development
# edit POSTGRES_PASSWORD, GRAFANA_ADMIN_PASSWORD, ONCALL_TOKEN

docker compose --env-file .env.development up -d --build --wait
curl -fsS http://127.0.0.1:8000/health
```

### 1.2 Start the observability stack

```bash
docker compose --env-file .env.development \
  -f observability/docker-compose.observability.yml up -d --wait
```

Endpoints (all bound to `127.0.0.1`):

| Service | URL |
|---|---|
| Grafana | `http://127.0.0.1:3000` (admin / `GRAFANA_ADMIN_PASSWORD`) |
| Prometheus | `http://127.0.0.1:9090` |
| Alertmanager | `http://127.0.0.1:9093` |
| On-call responder | `http://127.0.0.1:8080/health` |
| OTLP/HTTP receiver | `http://127.0.0.1:4318` |
| Application metrics (Prometheus format) | `http://127.0.0.1:8889/metrics` |

The application container reaches the collector through
`host.docker.internal:4318`, which Compose maps with
`extra_hosts: host.docker.internal:host-gateway`. Set `OTEL_ENABLED=false` in
the env file when the observability stack is not running.

### 1.3 Stop

```bash
docker compose --env-file .env.development -f observability/docker-compose.observability.yml down
docker compose --env-file .env.development down          # keeps the DB volume
```

`down -v` deletes the environment's database and telemetry volumes. It needs
explicit approval (deployment runbook, rule 10).

---

## 2. What is instrumented

The backend configures OpenTelemetry in `backend/app/observability/setup.py`:

| Signal | Instrumentation | Exporter |
|---|---|---|
| Traces | FastAPI requests, outbound HTTPX calls, `analysis.process_job` spans in the worker | OTLP/HTTP `/v1/traces` |
| Metrics | Application instruments plus FastAPI server metrics | OTLP/HTTP `/v1/metrics` |
| Logs | Root logging handler bridged to OTel, `trace_id`/`span_id` correlated | OTLP/HTTP `/v1/logs` |

Configuration (all optional; see [`backend/app/core/config.py`](../backend/app/core/config.py)):

| Variable | Default | Meaning |
|---|---|---|
| `OTEL_ENABLED` | `false` | Master switch. Disabled means no exporter, and the app behaves exactly as before. |
| `OTEL_SERVICE_NAME` | `chesspulse-api` | Resource `service.name`. The worker appends `-worker`. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | empty | OTLP/HTTP base URL. Empty while enabled logs a warning and exports nothing. |
| `OTEL_EXPORTER_OTLP_HEADERS` | empty | Standard `key=value,key2=value2`, URL-decoded. Use for Grafana Cloud auth. |
| `OTEL_TRACES_SAMPLER_ARG` | `1.0` | Root trace sampling ratio. Production should be `0.1` or lower. |
| `OTEL_METRIC_EXPORT_INTERVAL_MS` | `15000` | Metric export interval. |
| `OTEL_LOGS_ENABLED` | `true` | Attach the OTel log handler. |

Deliberate properties:

- **Telemetry never breaks the app.** Setup failures are caught, logged once by
  type name only, and the process continues without exporters. `/health` does
  not depend on the collector.
- **Tests need no collector.** `OTEL_ENABLED` defaults to false.
- **No raw URLs in labels.** The HTTP metric uses the FastAPI route template,
  so a username does not create a new time series.
- **No secrets in telemetry.** Log extras never contain `DATABASE_URL`, tokens
  or headers; the setup catches exporter errors without printing them.
- **No SQLAlchemy statement spans.** `opentelemetry-instrumentation-sqlalchemy`
  0.66b2 only supports SQLAlchemy `< 2.1.0`, and this project uses 2.1.5. DB time
  is visible through request latency and `/health`, not as a span. Revisit when
  the instrumentation package supports SQLAlchemy 2.1.
- **The exporter's own log records are filtered** out of the OTLP log stream, so
  an unreachable backend cannot generate an export loop.

### 2.1 Running without Docker

```bash
# API
backend/.venv/Scripts/python.exe -m uvicorn app.main:create_app --factory --reload

# Worker (separate process)
backend/.venv/Scripts/python.exe -m app.worker
```

Set `OTEL_ENABLED=true` and an endpoint to export; leave it false otherwise.

---

## 3. Application metrics

Defined in [`backend/app/observability/metrics.py`](../backend/app/observability/metrics.py).
Metric names are OpenTelemetry names; the Collector translates them to
Prometheus (dots → underscores, counters get `_total`, unit `s` becomes
`_seconds`).

| OTel instrument | Prometheus name | Type | Labels | Recorded when |
|---|---|---|---|---|
| `chesspulse.http.server.requests` | `chesspulse_http_server_requests_total` | counter | `http_request_method`, `http_route`, `http_response_status_code` | every API request except `/health` and `/metrics` |
| `chesspulse.http.server.duration` | `chesspulse_http_server_duration_seconds` | histogram | same | same |
| `chesspulse.provider.requests` | `chesspulse_provider_requests_total` | counter | `chesspulse_provider_resource`, `chesspulse_provider_outcome` | every Chess.com call; outcome is `success` or a `ProviderErrorCode` |
| `chesspulse.provider.duration` | `chesspulse_provider_duration_seconds` | histogram | same | same |
| `chesspulse.cache.refreshes` | `chesspulse_cache_refreshes_total` | counter | `chesspulse_cache_outcome` | every dataset refresh; `succeeded` or an error code |
| `chesspulse.cache.refresh.duration` | `chesspulse_cache_refresh_duration_seconds` | histogram | same | same |
| `chesspulse.analysis.jobs` | `chesspulse_analysis_jobs_total` | counter | `chesspulse_analysis_outcome` | every claimed analysis job: `completed`, `failed`, `retry` |
| `chesspulse.analysis.job.duration` | `chesspulse_analysis_job_duration_seconds` | histogram | same | same |
| `chesspulse.ingestion.games` | `chesspulse_ingestion_games_total` | counter | `chesspulse_ingestion_complete` | after a successful refresh |
| `chesspulse.board.operations` | `chesspulse_board_operations_total` | counter | `chesspulse_board_operation`, `chesspulse_board_outcome` | every free-board `evaluate` / `analyze_move` |
| `chesspulse.board.operation.duration` | `chesspulse_board_operation_duration_seconds` | histogram | same | same |

Why these metrics: they answer the questions the product actually raises —
"is the API failing", "is Chess.com down", "did ingestion store data", "is the
engine keeping up", "is the free board broken" — without user identifiers,
which keeps cardinality bounded on a free tier.

The label values are bounded sets (routes, error codes, outcomes). Do not add a
username, FEN, game id or free-text label.

### 3.1 Verify the live metric names

Translation is a Collector concern. Before trusting a dashboard or an alert,
read the endpoint the Collector exposes:

```bash
curl -s http://127.0.0.1:8889/metrics | grep '^chesspulse_'
```

If a name differs, update
[`observability/prometheus/alerts.yml`](../observability/prometheus/alerts.yml),
the dashboard JSON and this table together — `scripts/check-observability-config.py`
fails on an unknown metric name.

---

## 4. Dashboard

Provisioned dashboard: `ChessPulse → ChessPulse — application overview`
([JSON](../observability/grafana/dashboards/chesspulse-overview.json)).

Panels:

1. HTTP request rate by route.
2. 5xx error ratio (thresholds at 1% and 5%).
3. p95 HTTP latency (thresholds at 1 s and 2 s).
4. Chess.com request outcomes (stacked by error code).
5. Dataset refreshes by outcome.
6. Engine analysis jobs by outcome.
7. Eligible games ingested per hour.
8. Free-board operations by operation and outcome.

The datasource list also provisions Tempo (traces) and Loki (logs) with a
derived field: a log line containing `trace_id=...` links to the trace, and a
trace links back to logs in the same window.

Grafana provisioning is `allowUiUpdates: false`; edit the JSON in the repository
and restart Grafana to make a permanent change.

---

## 5. Alerts

Rules: [`observability/prometheus/alerts.yml`](../observability/prometheus/alerts.yml).
Alertmanager routes every group to the on-call responder, including resolved
alerts.

| Alert | Expression (summary) | For | Severity |
|---|---|---|---|
| `ChessPulseHighErrorRate` | 5xx share of requests > 5% | 5m | critical |
| `ChessPulseHighLatencyP95` | p95 request duration > 2 s | 10m | warning |
| `ChessPulseProviderFailureRate` | non-success provider share > 30% | 10m | warning |
| `ChessPulseCacheRefreshFailing` | ≥ 3 failed refreshes in 15m | 5m | warning |
| `ChessPulseAnalysisFailureRate` | failed analysis share > 30% | 10m | warning |
| `ChessPulseBoardErrors` | any board engine error in 10m | 5m | warning |
| `ChessPulseMetricsMissing` | `up{job="chesspulse-app"} == 0` | 5m | critical |
| `ChessPulseNoTraffic` | no HTTP requests in 30m | 30m | info |

`ChessPulseNoTraffic` is informational on purpose: a free Render instance sleeps
after 15 idle minutes. Do not "fix" it by pinging the service from CI, which
would consume free instance hours.

Validate the rules without Docker:

```bash
python scripts/check-observability-config.py
```

It parses every YAML/JSON file, checks the metric and label names against the
instruments the backend emits, and checks that every `runbook` annotation points
at a heading in this document.

### High error rate

`ChessPulseHighErrorRate` means the API answers 5xx for more than 5% of
requests. Provider timeouts surface as 502/504 and also count here.

1. `curl -fsS <base>/health` — liveness only, not the database.
2. Request a database-backed endpoint (overview) and read the status and
   `data_status`.
3. Read the API log for the failing route and error code.
4. If the database is expired or unreachable, restore/recreate it
   (deployment runbook 10.5); redeploying does not fix a provider outage.
5. If the errors started with a deploy, roll back to the previous known-good
   commit and verify again.

### High latency

1. Decide whether the instance is cold. A free Render instance sleeps after 15
   idle minutes and takes about a minute to wake.
2. Check provider latency and refresh activity; the first refresh for a player
   calls Chess.com several times.
3. Check CPU pressure. Stockfish work on a 0.1 CPU free instance blocks request
   handling.
4. Do not raise `ANALYSIS_DEPTH` / `ANALYSIS_THREADS` on a free instance.

### Provider failures

1. Confirm the failure codes in the provider panel (429, timeout, 5xx,
   invalid response).
2. A 429 is rate limiting; the client already backs off and respects
   `Retry-After`.
3. Confirm cached data is served with `data_status: "stale"`; a failed refresh
   never deletes rows.
4. Do not redeploy. Wait for the provider.

### Cache refresh failures

1. Read `chesspulse_cache_outcome`: a provider code, an ingestion failure or a
   database error.
2. Check database connectivity and disk space.
3. Confirm the last successful data is still served as `stale`.
4. Respect the failure cooldown; do not repeatedly retry the provider.

### Analysis failures

1. Check that `STOCKFISH_PATH` points at an executable binary.
2. Read the worker log for engine codes (timeout, crash, rejected PGN).
3. On Render, confirm `RUN_EMBEDDED_WORKER=1`; jobs stay `queued` without it.
4. Requeue stale jobs only after the engine is healthy.

### Board errors

1. `503 ENGINE_UNAVAILABLE` means Stockfish is missing or not executable in
   the image.
2. Reproduce with `POST /api/v1/board/evaluate` and read the error code.
3. The board uses one long-lived engine behind a lock; concurrent requests wait
   rather than start a second engine.

### Metrics missing

1. Check the Collector and Prometheus containers.
2. Search the application log for `OpenTelemetry setup failed`.
3. Verify `OTEL_ENABLED=true` and that the endpoint and headers are valid.
4. The application may be healthy while telemetry is blind — verify `/health`
   and a database-backed request separately.

### No traffic

1. Expected while a free Render instance sleeps.
2. If a user reports an outage, wake the instance and re-check.
3. If the Collector is down, the absence of data proves nothing.

---

## 6. AI on-call responder

Source: [`observability/oncall/`](../observability/oncall/). It is a small
FastAPI service with no database.

Flow:

```
Prometheus rule fires
  -> Alertmanager groups and POSTs /alerts (Bearer token)
    -> on-call responder authorises the request
      -> deterministic runbook diagnosis (always)
      -> optional LLM triage (OpenAI-compatible /chat/completions)
      -> optional notification webhook
    <- 200 with the diagnosis
```

Endpoints:

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/health` | none | liveness, current mode (`runbook` or `llm`) |
| `GET` | `/runbooks` | Bearer | alert name → runbook document |
| `POST` | `/alerts` | Bearer | Alertmanager webhook |

Behaviour guarantees:

- Missing or wrong token → `401`; unset token → `503` (fail closed, never accept
  forged alerts).
- No `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` → deterministic runbook mode.
  This is the default and is fully supported.
- LLM error, timeout or malformed response → the deterministic diagnosis is
  returned with `mode: "llm-fallback"`. The model can never block alerting.
- Resolved alerts are accepted; in LLM mode they are answered with a
  confirmation instead of a triage.
- The token is compared in constant time, is never logged and never appears in
  a command line.
- Alert text is untrusted: control characters are stripped and fields are
  truncated before they reach the model.
- The notification webhook is best effort; its failure is logged by exception
  type only (the URL may embed a token).

Configuration:

| Variable | Required | Meaning |
|---|---|---|
| `ONCALL_TOKEN` | yes | Shared secret for `Authorization: Bearer`. Generate a random value. |
| `ONCALL_ENVIRONMENT` | no | Echoed in responses and notifications. |
| `ALERT_WEBHOOK_URL` | no | Where the diagnosis summary is posted. Empty = log only. |
| `LLM_BASE_URL` | no | OpenAI-compatible base, e.g. `https://api.openai.com/v1`. |
| `LLM_API_KEY` | no | Sent as `Authorization: Bearer`. Never logged. |
| `LLM_MODEL` | no | Model name. |
| `LLM_TIMEOUT_SECONDS` | no | Default 20. |

Run its tests (no network, mocked LLM):

```bash
cd observability/oncall
python -m pytest -q
ruff check .
mypy app.py
```

### 6.1 Local smoke test

```bash
# 1. health
curl -fsS http://127.0.0.1:8080/health

# 2. authenticated alert
curl -fsS -X POST http://127.0.0.1:8080/alerts \
  -H "Authorization: Bearer $ONCALL_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"version":"4","status":"firing","alerts":[{"status":"firing","labels":{"alertname":"ChessPulseHighErrorRate","severity":"critical"},"annotations":{"summary":"smoke test"},"fingerprint":"smoke"}]}'
```

Expected: `received: 1` and a diagnosis with `mode: "runbook"` unless an LLM is
configured. A `401` means the token is wrong; `503` means it is not configured.

---

## 7. Production on Render (free tier)

Render Free cannot host Prometheus, Loki, Tempo, Grafana or Alertmanager: there
is no free always-on volume and no free private service. Two supported options:

1. **Grafana Cloud free tier** — send OTLP from Render directly. Set in the
   Render dashboard (not in git):

   ```
   OTEL_ENABLED=true
   OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-<region>.grafana.net/otlp
   OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic <base64(instanceId:token)>
   OTEL_TRACES_SAMPLER_ARG=0.1
   OTEL_METRIC_EXPORT_INTERVAL_MS=30000
   ```

   `OTEL_SERVICE_NAME`, `OTEL_TRACES_SAMPLER_ARG` and
   `OTEL_METRIC_EXPORT_INTERVAL_MS` are set in `render.yaml`; the endpoint and
   headers are deliberately `sync: false` so a blueprint sync never overwrites
   them and never commits a secret.

2. **Self-hosted stack on a VM** — run the application Compose stack and
   `observability/docker-compose.observability.yml` on the same host, with
   `OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4318` (or the
   collector's address). This is the only path that includes the dashboard,
   Prometheus alert rules and the on-call responder.

Alerting on Render itself is not configured by this repository: the Render
dashboard can notify by email for deploy failures, but it cannot evaluate these
PromQL rules. Do not claim alerting works on Render until an OTLP destination
and a rule engine are actually configured.

### 7.1 Free-tier limits to respect

- Free web service: 0.1 CPU / 512 MB, sleeps after 15 idle minutes.
- Free PostgreSQL: 1 GB, expires 30 days after creation.
- Grafana Cloud free tier: bounded metrics/logs/traces retention and ingestion;
  keep sampling below 1.0 and do not enable every signal at full volume.
- The local stack is not a production SLA. One VM is a single point of failure.

---

## 8. Manual promotion to production

`.github/workflows/promote.yml` is the only path that deploys production.
A plain push to `main` does **not** deploy production:

- `ci.yml` runs backend, frontend, e2e and the observability config check.
- Its `deploy` job builds and pushes the image to GHCR and can call the
  **development** hook (`RENDER_DEV_DEPLOY_HOOK`) only.
- `promote.yml` is `workflow_dispatch` only, bound to the `production` GitHub
  Environment (configure required reviewers there).

Promotion steps:

1. Choose the exact commit SHA on `main`.
2. Run **Actions → Promote to production → Run workflow** with that SHA and
   `confirm=promote`.
3. The workflow verifies that the CI run for that SHA concluded `success`,
   then calls the Render API `POST /v1/services/{serviceId}/deploys` with
   `commitId` (secrets `RENDER_API_KEY`, `RENDER_SERVICE_ID`).
4. Verify the deployment with `docs/deployment.md` section 8.

`render.yaml` sets `autoDeploy: false`, so Render does not build on its own.
Without the two secrets the workflow fails before contacting Render; it never
falls back to deploying the branch head.

---

## 9. Files

| Path | Purpose |
|---|---|
| `backend/app/observability/` | SDK setup, metric instruments, HTTP middleware |
| `backend/tests/test_observability.py` | no-collector behaviour, header parsing, exporter wiring |
| `observability/otel-collector/config.yaml` | OTLP receiver and three exporters |
| `observability/prometheus/` | scrape config and alert rules |
| `observability/alertmanager/alertmanager.yml` | routing to the on-call responder |
| `observability/tempo/tempo.yaml`, `observability/loki/loki.yaml` | trace/log storage |
| `observability/grafana/` | datasources, dashboard provider, dashboard JSON |
| `observability/oncall/` | AI on-call service, tests, Dockerfile |
| `scripts/check-observability-config.py` | offline config and metric-name validation |
| `.github/workflows/promote.yml` | manual production promotion |
| `.env.development.example`, `.env.production.example` | environment templates |
