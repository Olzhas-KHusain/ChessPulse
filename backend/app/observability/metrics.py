"""Application-specific OpenTelemetry metrics.

Instruments are created from a real ``Meter`` only when observability is configured.
When it is not, every ``record_*`` helper is a no-op, so tests and local runs do not
need a collector and cannot fail because telemetry is unavailable.

Metric names follow the OpenTelemetry naming convention; the Prometheus exporter in
the collector appends ``_total`` to counters and unit suffixes to histograms.
"""

from __future__ import annotations

from opentelemetry.metrics import Counter, Histogram, Meter
from opentelemetry.util.types import Attributes

# Prometheus label names after OTel -> Prometheus sanitisation.
HTTP_METHOD = "http.request.method"
HTTP_ROUTE = "http.route"
HTTP_STATUS = "http.response.status_code"
PROVIDER_RESOURCE = "chesspulse.provider.resource"
PROVIDER_OUTCOME = "chesspulse.provider.outcome"
CACHE_OUTCOME = "chesspulse.cache.outcome"
ANALYSIS_OUTCOME = "chesspulse.analysis.outcome"
INGESTION_COMPLETE = "chesspulse.ingestion.complete"
BOARD_OPERATION = "chesspulse.board.operation"
BOARD_OUTCOME = "chesspulse.board.outcome"


class Metrics:
    """Counters and histograms owned by one meter."""

    def __init__(self, meter: Meter) -> None:
        self.http_requests: Counter = meter.create_counter(
            "chesspulse.http.server.requests",
            unit="{request}",
            description="HTTP requests handled by the API, by route and status.",
        )
        self.http_duration: Histogram = meter.create_histogram(
            "chesspulse.http.server.duration",
            unit="s",
            description="HTTP request duration, by route and status.",
        )
        self.provider_requests: Counter = meter.create_counter(
            "chesspulse.provider.requests",
            unit="{request}",
            description="Chess.com requests, by resource and outcome.",
        )
        self.provider_duration: Histogram = meter.create_histogram(
            "chesspulse.provider.duration",
            unit="s",
            description="Chess.com request duration, by resource and outcome.",
        )
        self.cache_refreshes: Counter = meter.create_counter(
            "chesspulse.cache.refreshes",
            unit="{refresh}",
            description="Player dataset refresh attempts, by outcome.",
        )
        self.cache_duration: Histogram = meter.create_histogram(
            "chesspulse.cache.refresh.duration",
            unit="s",
            description="Player dataset refresh duration, by outcome.",
        )
        self.analysis_jobs: Counter = meter.create_counter(
            "chesspulse.analysis.jobs",
            unit="{job}",
            description="Engine analysis jobs, by outcome.",
        )
        self.analysis_duration: Histogram = meter.create_histogram(
            "chesspulse.analysis.job.duration",
            unit="s",
            description="Engine analysis job duration, by outcome.",
        )
        self.ingested_games: Counter = meter.create_counter(
            "chesspulse.ingestion.games",
            unit="{game}",
            description="Eligible games stored by a successful dataset refresh.",
        )
        self.board_operations: Counter = meter.create_counter(
            "chesspulse.board.operations",
            unit="{operation}",
            description="Free-board engine operations, by operation and outcome.",
        )
        self.board_duration: Histogram = meter.create_histogram(
            "chesspulse.board.operation.duration",
            unit="s",
            description="Free-board engine operation duration, by operation and outcome.",
        )

    def record_http(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        attributes: Attributes = {
            HTTP_METHOD: method,
            HTTP_ROUTE: route,
            HTTP_STATUS: status_code,
        }
        self.http_requests.add(1, attributes)
        self.http_duration.record(duration_seconds, attributes)

    def record_provider(self, *, resource: str, outcome: str, duration_seconds: float) -> None:
        attributes: Attributes = {
            PROVIDER_RESOURCE: resource,
            PROVIDER_OUTCOME: outcome,
        }
        self.provider_requests.add(1, attributes)
        self.provider_duration.record(duration_seconds, attributes)

    def record_cache_refresh(self, *, outcome: str, duration_seconds: float) -> None:
        attributes: Attributes = {CACHE_OUTCOME: outcome}
        self.cache_refreshes.add(1, attributes)
        self.cache_duration.record(duration_seconds, attributes)

    def record_analysis_job(self, *, outcome: str, duration_seconds: float) -> None:
        attributes: Attributes = {ANALYSIS_OUTCOME: outcome}
        self.analysis_jobs.add(1, attributes)
        self.analysis_duration.record(duration_seconds, attributes)

    def record_ingestion(self, *, games: int, complete: bool) -> None:
        self.ingested_games.add(max(0, games), {INGESTION_COMPLETE: complete})

    def record_board_operation(
        self, *, operation: str, outcome: str, duration_seconds: float
    ) -> None:
        attributes: Attributes = {
            BOARD_OPERATION: operation,
            BOARD_OUTCOME: outcome,
        }
        self.board_operations.add(1, attributes)
        self.board_duration.record(duration_seconds, attributes)


_metrics: Metrics | None = None


def configure_metrics(meter: Meter) -> Metrics:
    """Install the process-wide metrics recorder.

    Called once from the observability setup. Tests may install their own meter and
    call :func:`reset_metrics` afterwards.
    """
    global _metrics
    _metrics = Metrics(meter)
    return _metrics


def reset_metrics() -> None:
    global _metrics
    _metrics = None


def get_metrics() -> Metrics | None:
    return _metrics


def record_http_request(
    *, method: str, route: str, status_code: int, duration_seconds: float
) -> None:
    if _metrics is not None:
        _metrics.record_http(
            method=method,
            route=route,
            status_code=status_code,
            duration_seconds=duration_seconds,
        )


def record_provider_request(resource: str, outcome: str, duration_seconds: float) -> None:
    if _metrics is not None:
        _metrics.record_provider(
            resource=resource, outcome=outcome, duration_seconds=duration_seconds
        )


def record_cache_refresh(outcome: str, duration_seconds: float) -> None:
    if _metrics is not None:
        _metrics.record_cache_refresh(outcome=outcome, duration_seconds=duration_seconds)


def record_analysis_job(outcome: str, duration_seconds: float) -> None:
    if _metrics is not None:
        _metrics.record_analysis_job(outcome=outcome, duration_seconds=duration_seconds)


def record_ingestion(games: int, complete: bool) -> None:
    if _metrics is not None:
        _metrics.record_ingestion(games=games, complete=complete)


def record_board_operation(operation: str, outcome: str, duration_seconds: float) -> None:
    if _metrics is not None:
        _metrics.record_board_operation(
            operation=operation, outcome=outcome, duration_seconds=duration_seconds
        )
