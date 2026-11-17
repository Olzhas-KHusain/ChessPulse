"""OpenTelemetry package: metrics, tracing setup and HTTP middleware."""

from app.observability.metrics import (
    Metrics,
    configure_metrics,
    get_metrics,
    record_analysis_job,
    record_board_operation,
    record_cache_refresh,
    record_http_request,
    record_ingestion,
    record_provider_request,
    reset_metrics,
)
from app.observability.setup import Observability, configure_observability, current_tracer

__all__ = [
    "Metrics",
    "Observability",
    "configure_metrics",
    "configure_observability",
    "current_tracer",
    "get_metrics",
    "record_analysis_job",
    "record_board_operation",
    "record_cache_refresh",
    "record_http_request",
    "record_ingestion",
    "record_provider_request",
    "reset_metrics",
]
