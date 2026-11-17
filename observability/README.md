# Observability stack

Self-hosted, free, and local-only by default. Full documentation:
[`docs/observability.md`](../docs/observability.md).

| Path | Component |
|---|---|
| `otel-collector/config.yaml` | OTLP/HTTP + gRPC receiver; Tempo, Prometheus and Loki exporters |
| `prometheus/prometheus.yml` | scrape config |
| `prometheus/alerts.yml` | ChessPulse alert rules |
| `alertmanager/alertmanager.yml` | routes every alert to the on-call responder |
| `tempo/tempo.yaml` | trace storage (24 h) |
| `loki/loki.yaml` | log storage (72 h) |
| `grafana/` | provisioned datasources and the ChessPulse dashboard |
| `oncall/` | AI on-call responder (FastAPI, optional LLM, deterministic fallback) |

## Run it

```bash
cp .env.development.example .env.development
# set POSTGRES_PASSWORD, GRAFANA_ADMIN_PASSWORD, ONCALL_TOKEN

docker compose --env-file .env.development up -d --build --wait
docker compose --env-file .env.development \
  -f observability/docker-compose.observability.yml up -d --wait
```

Then:

- Grafana `http://127.0.0.1:3000` → folder **ChessPulse** → *ChessPulse — application overview*.
- Prometheus `http://127.0.0.1:9090/alerts`.
- On-call `http://127.0.0.1:8080/health`.

The application reaches the collector through `host.docker.internal:4318`.
Set `OTEL_ENABLED=false` in the env file to run without telemetry.

## Verify before trusting

```bash
# Metric names as translated by the collector
curl -s http://127.0.0.1:8889/metrics | grep '^chesspulse_'

# Configuration, metric names and alert runbooks
python scripts/check-observability-config.py

# On-call service
cd observability/oncall && python -m pytest -q
```

## Rules

- Every port is bound to `127.0.0.1`. This stack has no authentication of its
  own (except the on-call bearer token) and must not be exposed.
- No paid plan, no cloud dependency. Grafana Cloud is an optional *export
  destination*, not a requirement.
- Secrets (`GRAFANA_ADMIN_PASSWORD`, `ONCALL_TOKEN`, `LLM_API_KEY`, OTLP headers)
  live in the git-ignored env file or the deployment dashboard, never here.
- `/health` must not depend on this stack.
