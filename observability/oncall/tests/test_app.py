"""On-call responder: auth, deterministic runbooks, LLM path and fallback."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app import Settings, create_app

TOKEN = "test-oncall-token"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "oncall_token": SecretStr(TOKEN),
        "oncall_environment": "test",
        "llm_base_url": "",
        "llm_api_key": SecretStr(""),
        "llm_model": "",
        "alert_webhook_url": "",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def _payload(alertname: str = "ChessPulseHighErrorRate", status: str = "firing") -> dict[str, object]:
    return {
        "version": "4",
        "status": status,
        "groupKey": "{}:{alertname}",
        "alerts": [
            {
                "status": status,
                "labels": {"alertname": alertname, "severity": "critical", "service": "chesspulse"},
                "annotations": {
                    "summary": "ChessPulse returns 5xx for more than 5% of requests",
                    "description": "The API error ratio is 12% over the last 5 minutes.",
                },
                "fingerprint": "abc123",
            }
        ],
    }


def _client(**overrides: object) -> TestClient:
    return TestClient(create_app(_settings(**overrides)))


def test_health_reports_runbook_mode() -> None:
    response = _client().get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == "runbook"
    assert body["environment"] == "test"


def test_alerts_require_a_bearer_token() -> None:
    client = _client()
    assert client.post("/alerts", json=_payload()).status_code == 401
    assert (
        client.post("/alerts", json=_payload(), headers={"Authorization": "Bearer wrong"}).status_code
        == 401
    )


def test_missing_token_fails_closed() -> None:
    client = _client(oncall_token=SecretStr(""))
    response = client.post(
        "/alerts", json=_payload(), headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 503


def test_deterministic_runbook_diagnosis() -> None:
    client = _client()
    response = client.post(
        "/alerts", json=_payload(), headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["received"] == 1
    assert body["mode"] == "runbook"
    diagnosis = body["alerts"][0]["diagnosis"]
    assert diagnosis["alertname"] == "ChessPulseHighErrorRate"
    assert diagnosis["mode"] == "runbook"
    assert diagnosis["title"] == "API 5xx error rate"
    assert diagnosis["actions"]
    assert diagnosis["runbook"] == "docs/observability.md#high-error-rate"


def test_unknown_alert_uses_the_default_runbook() -> None:
    client = _client()
    response = client.post(
        "/alerts", json=_payload("SomethingElse"), headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 200
    diagnosis = response.json()["alerts"][0]["diagnosis"]
    assert diagnosis["title"] == "Unrecognised alert"
    assert diagnosis["runbook"] == "docs/deployment.md#11-troubleshooting"


def test_resolved_alerts_are_accepted() -> None:
    client = _client()
    response = client.post(
        "/alerts",
        json=_payload(status="resolved"),
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "resolved"


def test_empty_alert_list_is_rejected() -> None:
    client = _client()
    response = client.post(
        "/alerts",
        json={"version": "4", "status": "firing", "alerts": []},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 400


def test_llm_diagnosis_is_used_when_configured() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer llm-secret"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "1. Check /health\n2. Read the API log\n3. Verify PostgreSQL"}}
                ]
            },
        )

    app = create_app(
        _settings(
            llm_base_url="https://llm.example/v1",
            llm_api_key=SecretStr("llm-secret"),
            llm_model="test-model",
        ),
        transport=httpx.MockTransport(handler),
    )
    response = TestClient(app).post(
        "/alerts", json=_payload(), headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "llm"
    diagnosis = body["alerts"][0]["diagnosis"]
    assert diagnosis["mode"] == "llm"
    assert "Check /health" in diagnosis["summary"]


def test_llm_failure_falls_back_to_the_runbook() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "upstream down"})

    app = create_app(
        _settings(
            llm_base_url="https://llm.example/v1",
            llm_api_key=SecretStr("llm-secret"),
            llm_model="test-model",
        ),
        transport=httpx.MockTransport(handler),
    )
    response = TestClient(app).post(
        "/alerts", json=_payload(), headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 200
    diagnosis = response.json()["alerts"][0]["diagnosis"]
    assert diagnosis["mode"] == "llm-fallback"
    assert diagnosis["actions"]


def test_runbooks_require_a_token() -> None:
    client = _client()
    assert client.get("/runbooks").status_code == 401
    response = client.get("/runbooks", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200
    assert "ChessPulseHighErrorRate" in response.json()
