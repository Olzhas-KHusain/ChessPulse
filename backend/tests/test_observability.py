"""OpenTelemetry setup, metric helpers and the no-collector fallback (no network)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from app.core.config import Settings
from app.observability import (
    configure_metrics,
    configure_observability,
    record_analysis_job,
    record_board_operation,
    record_cache_refresh,
    record_http_request,
    record_ingestion,
    record_provider_request,
    reset_metrics,
)
from app.observability.setup import parse_otlp_headers


@pytest.fixture(autouse=True)
def _reset_global_metrics() -> Iterator[None]:
    reset_metrics()
    yield
    reset_metrics()


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "_env_file": None,
        "database_url": "postgresql+psycopg://u:secret@localhost:1/db",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_parse_otlp_headers_handles_space_and_encoding() -> None:
    headers = parse_otlp_headers("Authorization=Basic%20abc, X-Scope-OrgID=tenant, broken, =empty")
    assert headers == {"Authorization": "Basic abc", "X-Scope-OrgID": "tenant"}


def test_parse_otlp_headers_empty() -> None:
    assert parse_otlp_headers("") == {}
    assert parse_otlp_headers("no-pairs") == {}


def test_disabled_telemetry_is_a_noop() -> None:
    handle = configure_observability(FastAPI(), _settings(otel_enabled=False))
    # Shutdown must be safe even when nothing was configured.
    handle.shutdown()


def test_enabled_without_endpoint_does_not_export() -> None:
    handle = configure_observability(
        FastAPI(), _settings(otel_enabled=True, otel_exporter_otlp_endpoint="")
    )
    assert handle.tracer_provider is None
    assert handle.meter_provider is None
    handle.shutdown()


def test_metric_helpers_are_safe_without_a_meter() -> None:
    # No configure_metrics call: everything must be a silent no-op.
    record_http_request(method="GET", route="/health", status_code=200, duration_seconds=0.01)
    record_provider_request("profile", "success", 0.01)
    record_cache_refresh("succeeded", 0.01)
    record_analysis_job("completed", 0.5)
    record_ingestion(3, True)
    record_board_operation("evaluate", "success", 0.01)


def test_metrics_are_exported_to_a_reader() -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    configure_metrics(provider.get_meter("chesspulse-test"))
    try:
        record_http_request(
            method="GET",
            route="/api/v1/players/{username}/overview",
            status_code=200,
            duration_seconds=0.25,
        )
        record_provider_request("month_archive", "UPSTREAM_TIMEOUT", 1.5)
        record_cache_refresh("succeeded", 2.0)
        record_analysis_job("completed", 3.0)
        record_ingestion(7, complete=True)
        record_board_operation("analyze_move", "success", 0.4)

        data = reader.get_metrics_data()
    finally:
        provider.shutdown()

    assert data is not None
    names = {
        metric.name
        for resource_metrics in data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
    }
    assert "chesspulse.http.server.requests" in names
    assert "chesspulse.provider.requests" in names
    assert "chesspulse.cache.refreshes" in names
    assert "chesspulse.analysis.jobs" in names
    assert "chesspulse.ingestion.games" in names
    assert "chesspulse.board.operations" in names
