"""OpenTelemetry wiring for the API and the analysis worker.

Telemetry is deliberately best-effort: a missing collector, an expired Grafana Cloud
token or an exporter bug must never stop the application from serving requests. Setup
failures are logged once and the process continues without an exporter.

The OTLP/HTTP endpoint is the *base* URL (for example ``http://localhost:4318`` or a
Grafana Cloud gateway); the per-signal paths ``/v1/traces``, ``/v1/metrics`` and
``/v1/logs`` are appended here.
"""

from __future__ import annotations

import logging
import os
import socket
from dataclasses import dataclass
from urllib.parse import unquote

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from app import __version__
from app.core.config import Settings
from app.observability.metrics import configure_metrics
from app.observability.middleware import MetricsMiddleware

logger = logging.getLogger(__name__)

_SERVICE_VERSION = __version__
_EXPORTER_TIMEOUT_SECONDS = 10.0


class _ExporterNoiseFilter(logging.Filter):
    """Keep the SDK's own diagnostics out of the OTLP log stream.

    Exporting the exporter's failure messages would recurse (the handler sees its
    own warning) and would flood the backend during an outage. They still go to
    stdout through the normal handler.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith("opentelemetry")


@dataclass
class Observability:
    """Handles that must be flushed and closed when the process exits."""

    tracer_provider: TracerProvider | None = None
    meter_provider: MeterProvider | None = None
    logger_provider: LoggerProvider | None = None
    log_handler: LoggingHandler | None = None

    def shutdown(self) -> None:
        if self.log_handler is not None:
            logging.getLogger().removeHandler(self.log_handler)
            self.log_handler = None
        if self.tracer_provider is not None:
            self.tracer_provider.shutdown()
        if self.meter_provider is not None:
            self.meter_provider.shutdown()
        if self.logger_provider is not None:
            self.logger_provider.shutdown()


def parse_otlp_headers(raw: str) -> dict[str, str]:
    """Parse the standard ``OTEL_EXPORTER_OTLP_HEADERS`` form.

    ``Authorization=Basic%20abc, X-Scope-OrgID=tenant`` becomes a normal mapping.
    Values are URL-decoded; keys are stripped. Empty pairs are ignored.
    """
    headers: dict[str, str] = {}
    for pair in raw.split(","):
        key, separator, value = pair.partition("=")
        key = key.strip()
        if separator and key:
            headers[key] = unquote(value.strip())
    return headers


def _signal_endpoint(base: str, signal: str) -> str:
    suffix = f"/v1/{signal}"
    return base if base.endswith(suffix) else f"{base}{suffix}"


def _resource(settings: Settings, service_name: str) -> Resource:
    return Resource.create(
        {
            "service.name": service_name,
            "service.version": _SERVICE_VERSION,
            "service.instance.id": f"{socket.gethostname()}-{os.getpid()}",
            "deployment.environment.name": settings.app_env,
        }
    )


def configure_observability(
    app: FastAPI | None,
    settings: Settings,
    *,
    service_name: str | None = None,
) -> Observability:
    """Configure OTLP exporters and instrument the process.

    Args:
        app: FastAPI app for HTTP instrumentation, or ``None`` for a worker.
        settings: Validated application settings.
        service_name: Override for the resource service name (the worker uses a
            distinct name so traces do not mix with API requests).

    SQLAlchemy statement spans are deliberately not enabled: the
    ``opentelemetry-instrumentation-sqlalchemy`` package refuses SQLAlchemy 2.1,
    so the engine is not passed here at all.

    Returns:
        An :class:`Observability` handle. Always safe to shut down, including when
        telemetry is disabled or setup failed.
    """
    if not settings.otel_enabled:
        return Observability()

    endpoint = settings.otel_exporter_otlp_endpoint
    if not endpoint:
        logger.warning(
            "OpenTelemetry is enabled but OTEL_EXPORTER_OTLP_ENDPOINT is empty; "
            "metrics, traces and logs will not be exported"
        )
        return Observability()

    try:
        headers = parse_otlp_headers(settings.otel_exporter_otlp_headers.get_secret_value())
        resource = _resource(settings, service_name or settings.otel_service_name)

        tracer_provider = TracerProvider(
            resource=resource,
            sampler=ParentBased(root=TraceIdRatioBased(settings.otel_traces_sampler_arg)),
        )
        tracer_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=_signal_endpoint(endpoint, "traces"),
                    headers=headers,
                    timeout=_EXPORTER_TIMEOUT_SECONDS,
                )
            )
        )
        trace.set_tracer_provider(tracer_provider)

        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(
                endpoint=_signal_endpoint(endpoint, "metrics"),
                headers=headers,
                timeout=_EXPORTER_TIMEOUT_SECONDS,
            ),
            export_interval_millis=settings.otel_metric_export_interval_ms,
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)
        configure_metrics(meter_provider.get_meter("chesspulse"))

        logger_provider: LoggerProvider | None = None
        log_handler: LoggingHandler | None = None
        if settings.otel_logs_enabled:
            logger_provider = LoggerProvider(resource=resource)
            logger_provider.add_log_record_processor(
                BatchLogRecordProcessor(
                    OTLPLogExporter(
                        endpoint=_signal_endpoint(endpoint, "logs"),
                        headers=headers,
                        timeout=_EXPORTER_TIMEOUT_SECONDS,
                    )
                )
            )
            set_logger_provider(logger_provider)
            log_handler = LoggingHandler(logger_provider=logger_provider)
            log_handler.addFilter(_ExporterNoiseFilter())
            logging.getLogger().addHandler(log_handler)

        LoggingInstrumentor().instrument(set_logging_format=False)
        HTTPXClientInstrumentor().instrument(tracer_provider=tracer_provider)
        if app is not None:
            FastAPIInstrumentor.instrument_app(
                app,
                tracer_provider=tracer_provider,
                meter_provider=meter_provider,
            )
            app.add_middleware(MetricsMiddleware)

        logger.info(
            "OpenTelemetry configured service=%s environment=%s endpoint=%s",
            service_name or settings.otel_service_name,
            settings.app_env,
            endpoint,
        )
        return Observability(
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            logger_provider=logger_provider,
            log_handler=log_handler,
        )
    except Exception as exc:  # telemetry must never break the application
        logger.warning(
            "OpenTelemetry setup failed (%s); continuing without exporters",
            type(exc).__name__,
        )
        return Observability()


def current_tracer() -> trace.Tracer:
    return trace.get_tracer("chesspulse")


__all__ = [
    "Observability",
    "configure_observability",
    "current_tracer",
    "parse_otlp_headers",
]
