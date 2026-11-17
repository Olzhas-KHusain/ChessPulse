"""ChessPulse AI on-call responder.

Receives Alertmanager webhooks, attaches a deterministic runbook diagnosis and —
when an OpenAI-compatible LLM is configured — asks the model for a short,
concrete triage. Notifications go to an optional webhook.

Design rules:

* The token is compared in constant time and is never logged.
* No LLM credential means deterministic runbook mode, not a broken service.
* An LLM failure falls back to the runbook and says so (`mode="llm-fallback"`).
* Alert payloads are untrusted text: they are truncated and never executed.
* Only labels/annotations are sent to the LLM; the service has no database or
  application secrets to leak.
"""

from __future__ import annotations

import hmac
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("chesspulse.oncall")

_MAX_FIELD_CHARS = 500
_MAX_PROMPT_CHARS = 4000
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class Settings(BaseSettings):
    """Environment configuration; every field has a safe default."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    oncall_token: SecretStr = SecretStr("")
    oncall_environment: str = "development"
    alert_webhook_url: str = ""
    llm_base_url: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    llm_timeout_seconds: float = 20.0
    log_level: str = "INFO"


class Alert(BaseModel):
    """One Alertmanager alert."""

    status: str = "firing"
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: str | None = None
    endsAt: str | None = None
    fingerprint: str | None = None
    generatorURL: str | None = None


class AlertmanagerPayload(BaseModel):
    version: str = "4"
    status: str = "firing"
    groupKey: str | None = None
    alerts: list[Alert] = Field(default_factory=list)


class Diagnosis(BaseModel):
    alertname: str
    severity: str
    status: str
    mode: str
    title: str
    summary: str
    actions: list[str]
    runbook: str


class AlertResult(BaseModel):
    fingerprint: str | None
    alertname: str
    diagnosis: Diagnosis


class Response(BaseModel):
    received: int
    status: str
    mode: str
    environment: str
    alerts: list[AlertResult]


@dataclass(frozen=True)
class Runbook:
    title: str
    actions: tuple[str, ...]
    doc: str


RUNBOOKS: dict[str, Runbook] = {
    "ChessPulseHighErrorRate": Runbook(
        title="API 5xx error rate",
        actions=(
            "Check /health, then a database-backed endpoint (overview).",
            "Read the API log for the failing route and error code.",
            "If the database is unreachable or expired, restore/recreate it; do not redeploy to fix an upstream.",
            "If a deploy correlates with the start, roll back to the previous known-good commit.",
        ),
        doc="docs/observability.md#high-error-rate",
    ),
    "ChessPulseHighLatencyP95": Runbook(
        title="High HTTP latency",
        actions=(
            "Confirm whether the instance is cold (free Render services sleep after 15 idle minutes).",
            "Check Chess.com provider latency and refresh activity in the dashboard.",
            "Check CPU pressure: Stockfish analysis on a free 0.1 CPU instance blocks other work.",
            "Do not raise analysis depth or threads on a free instance.",
        ),
        doc="docs/observability.md#high-latency",
    ),
    "ChessPulseProviderFailureRate": Runbook(
        title="Chess.com provider failures",
        actions=(
            "Confirm the provider is reachable from the host (do not paste credentials).",
            "Check the failure codes: 429 means rate limiting, 5xx/timeout means upstream.",
            "Verify cached data is served as `stale` and no data was deleted.",
            "Do not redeploy; a provider outage is not a ChessPulse regression.",
        ),
        doc="docs/observability.md#provider-failures",
    ),
    "ChessPulseCacheRefreshFailing": Runbook(
        title="Dataset refresh failures",
        actions=(
            "Identify whether `chesspulse_cache_outcome` is a provider code, an ingestion error or a DB error.",
            "Check database connectivity and disk space.",
            "Confirm `last_success_at` data is still served as `stale`.",
            "Wait for the failure cooldown before retrying; do not hammer the provider.",
        ),
        doc="docs/observability.md#cache-refresh-failures",
    ),
    "ChessPulseAnalysisFailureRate": Runbook(
        title="Engine analysis failures",
        actions=(
            "Check that `STOCKFISH_PATH` points at an executable binary.",
            "Check the worker log for engine codes (timeout, crash, rejected PGN).",
            "Confirm the worker is running (`RUN_EMBEDDED_WORKER=1` on Render).",
            "Requeue stale jobs only after the engine is healthy.",
        ),
        doc="docs/observability.md#analysis-failures",
    ),
    "ChessPulseBoardErrors": Runbook(
        title="Free board engine errors",
        actions=(
            "A 503 ENGINE_UNAVAILABLE means Stockfish is missing or not executable.",
            "Check serialized access: the board uses one long-lived engine behind a lock.",
            "Reproduce with a POST to /api/v1/board/evaluate and read the error code.",
        ),
        doc="docs/observability.md#board-errors",
    ),
    "ChessPulseMetricsMissing": Runbook(
        title="Application metrics missing",
        actions=(
            "Check that the OTel Collector is running and reachable on :4318.",
            "Check the application log for `OpenTelemetry setup failed` warnings.",
            "Confirm OTEL_ENABLED=true and the endpoint/headers are valid.",
            "The app may be healthy even when telemetry is blind; verify /health separately.",
        ),
        doc="docs/observability.md#metrics-missing",
    ),
    "ChessPulseNoTraffic": Runbook(
        title="No HTTP traffic",
        actions=(
            "Expected while a free Render instance is asleep; this is informational.",
            "If a user reports an outage, wake the instance and re-check /health.",
            "If the collector is down, no metrics arrive and this alert is meaningless.",
        ),
        doc="docs/observability.md#no-traffic",
    ),
}

_DEFAULT_RUNBOOK = Runbook(
    title="Unrecognised alert",
    actions=(
        "Open the alert in Alertmanager and identify the failing component.",
        "Check /health and the application log.",
        "Use docs/deployment.md section 11 (Troubleshooting).",
    ),
    doc="docs/deployment.md#11-troubleshooting",
)


def _clean(value: str, limit: int = _MAX_FIELD_CHARS) -> str:
    """Strip control characters and bound length for untrusted alert text."""
    return _CONTROL.sub("", value)[:limit]


def _runbook_for(alert: Alert) -> Runbook:
    return RUNBOOKS.get(alert.labels.get("alertname", ""), _DEFAULT_RUNBOOK)


def _summarise(alert: Alert, runbook: Runbook) -> str:
    summary = alert.annotations.get("summary") or f"{alert.labels.get('alertname', 'alert')} is firing"
    description = alert.annotations.get("description", "")
    parts = [f"{summary}"]
    if description:
        parts.append(description)
    parts.append(f"Runbook: {runbook.doc}")
    return "\n".join(parts)[:_MAX_PROMPT_CHARS]


class Diagnoser:
    """Deterministic runbook diagnosis plus optional LLM triage."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    @property
    def mode(self) -> str:
        configured = bool(
            self._settings.llm_base_url
            and self._settings.llm_model
            and self._settings.llm_api_key.get_secret_value()
        )
        return "llm" if configured else "runbook"

    def deterministic(self, alert: Alert) -> Diagnosis:
        runbook = _runbook_for(alert)
        alertname = _clean(alert.labels.get("alertname", "unknown"), 120)
        severity = _clean(alert.labels.get("severity", "warning"), 40)
        return Diagnosis(
            alertname=alertname,
            severity=severity,
            status=alert.status,
            mode="runbook",
            title=runbook.title,
            summary=_summarise(alert, runbook),
            actions=list(runbook.actions),
            runbook=runbook.doc,
        )

    async def diagnose(self, alert: Alert) -> Diagnosis:
        base = self.deterministic(alert)
        if self.mode != "llm":
            return base
        if alert.status == "resolved":
            return base.model_copy(
                update={
                    "summary": f"Resolved: {base.summary}",
                    "actions": ["Confirm the metric recovered and close the incident."],
                }
            )
        try:
            content = await self._ask_llm(alert, base)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            logger.warning("LLM diagnosis failed (%s); using the runbook", type(exc).__name__)
            return base.model_copy(update={"mode": "llm-fallback"})
        if not content:
            return base.model_copy(update={"mode": "llm-fallback"})
        return base.model_copy(update={"mode": "llm", "summary": content})

    async def _ask_llm(self, alert: Alert, base: Diagnosis) -> str:
        settings = self._settings
        prompt = (
            f"Alert: {base.alertname}\n"
            f"Severity: {base.severity}\n"
            f"Status: {alert.status}\n"
            f"Summary: {_clean(alert.annotations.get('summary', ''))}\n"
            f"Description: {_clean(alert.annotations.get('description', ''))}\n"
            f"Runbook: {base.runbook}\n"
            f"Deterministic actions: {'; '.join(base.actions)}\n"
        )[:_MAX_PROMPT_CHARS]
        payload = {
            "model": settings.llm_model,
            "temperature": 0,
            "max_tokens": 400,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the on-call assistant for ChessPulse, a free-tier FastAPI "
                        "application with PostgreSQL and Stockfish. Give at most five short, "
                        "concrete triage steps. Never invent metrics or claim a check was run. "
                        "Never ask for or print secrets. Prefer verifying before restarting."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {settings.llm_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(
            timeout=settings.llm_timeout_seconds, transport=self._transport
        ) as client:
            response = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data: Any = response.json()
        content = data["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            return ""
        return content.strip()[:_MAX_PROMPT_CHARS]


def _authorize(authorization: str | None, settings: Settings) -> None:
    expected = settings.oncall_token.get_secret_value()
    if not expected:
        # Fail closed: an unauthenticated responder would accept forged alerts.
        raise HTTPException(status_code=503, detail="on-call token is not configured")
    scheme, _, value = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(value.strip(), expected):
        raise HTTPException(
            status_code=401,
            detail="invalid on-call credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def _notify(settings: Settings, payload: AlertmanagerPayload, results: list[AlertResult]) -> None:
    if not settings.alert_webhook_url:
        return
    body = {
        "source": "chesspulse-oncall",
        "environment": settings.oncall_environment,
        "status": payload.status,
        "alerts": [result.model_dump() for result in results],
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(settings.alert_webhook_url, json=body)
            response.raise_for_status()
    except (httpx.HTTPError, OSError) as exc:
        # Notification failure is logged without the URL (it may embed a token).
        logger.warning("alert webhook failed (%s)", type(exc).__name__)


def create_app(
    settings: Settings | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    settings = settings or Settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    diagnoser = Diagnoser(settings, transport=transport)
    app = FastAPI(title="ChessPulse on-call responder", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.diagnoser = diagnoser

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "chesspulse-oncall",
            "mode": diagnoser.mode,
            "environment": settings.oncall_environment,
        }

    @app.get("/runbooks")
    async def runbooks(authorization: str | None = Header(default=None)) -> dict[str, str]:
        _authorize(authorization, settings)
        return {name: runbook.doc for name, runbook in RUNBOOKS.items()}

    @app.post("/alerts", response_model=Response)
    async def alerts(
        payload: AlertmanagerPayload,
        authorization: str | None = Header(default=None),
    ) -> Response:
        _authorize(authorization, settings)
        if not payload.alerts:
            raise HTTPException(status_code=400, detail="payload has no alerts")

        started = time.perf_counter()
        results = [
            AlertResult(
                fingerprint=alert.fingerprint,
                alertname=alert.labels.get("alertname", "unknown"),
                diagnosis=await diagnoser.diagnose(alert),
            )
            for alert in payload.alerts
        ]
        logger.info(
            "alert group processed alerts=%s status=%s mode=%s ms=%s",
            len(results),
            payload.status,
            diagnoser.mode,
            round((time.perf_counter() - started) * 1000),
        )
        await _notify(settings, payload, results)
        return Response(
            received=len(results),
            status=payload.status,
            mode=diagnoser.mode,
            environment=settings.oncall_environment,
            alerts=results,
        )

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover - container entrypoint uses uvicorn
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
    )
