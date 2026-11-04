"""Application factory, health, logging and the last-resort error handlers (no database)."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.logging import KeyValueFormatter
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    settings = Settings(_env_file=None, database_url="postgresql+psycopg://u:secret@localhost:1/db")
    app = create_app(settings)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    return TestClient(app, raise_server_exceptions=False)


def test_health_does_not_need_the_database(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/nope", headers={"X-Request-ID": "abc-123"})
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "The requested resource does not exist.",
            "request_id": "abc-123",
        }
    }


def test_unexpected_error_hides_details(client: TestClient) -> None:
    response = client.get("/boom", headers={"X-Request-ID": "<script>"})
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["request_id"] != "<script>"  # unsafe ids are replaced
    assert "secret" not in response.text and "RuntimeError" not in response.text


def test_method_not_allowed(client: TestClient) -> None:
    response = client.post("/health")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_log_extras_are_appended() -> None:
    record = logging.makeLogRecord(
        {"msg": "dataset refresh", "levelname": "INFO", "name": "x", "player": "abc"}
    )
    assert KeyValueFormatter("%(message)s").format(record) == "dataset refresh player='abc'"
