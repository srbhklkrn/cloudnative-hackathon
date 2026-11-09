"""OTLP/HTTP export. Deliberately excludes bodies, cookies, headers and search text."""
import logging
import os
from time import perf_counter
from urllib.parse import unquote

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import extract
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, StatusCode

tracer = trace.get_tracer("detour.http")
meter = metrics.get_meter("detour")
request_duration = meter.create_histogram("detour.request.duration", unit="s", description="API request duration")
search_duration = meter.create_histogram("detour.search.duration", unit="s", description="Session retrieval duration")
replan_duration = meter.create_histogram("detour.replan.duration", unit="s", description="Agenda replanning duration")
replans = meter.create_counter("detour.replan.attempts", description="Replanning outcomes")
disruptions = meter.create_counter("detour.disruptions", description="Persisted demo organizer changes")
alternatives = meter.create_histogram("detour.recommendations.count", description="Compatible replacements returned")
datastore_errors = meter.create_counter("detour.elasticsearch.errors", description="Failed datastore requests")
logger = logging.getLogger("detour")
_providers = None


def export_headers():
    raw = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
    headers = {}
    for entry in raw.split(","):
        key, separator, value = entry.strip().partition("=")
        if not separator or not key or not value or "\n" in value or "\r" in value:
            raise ValueError("OTEL headers must use name=URL-encoded-value entries; values omitted")
        decoded = unquote(value)
        if "\n" in decoded or "\r" in decoded:
            raise ValueError("Invalid OTEL header format; values omitted")
        headers[key] = decoded
    if not any(k.lower() == "authorization" and v.startswith("Bearer ") for k, v in headers.items()):
        raise ValueError("Dash0 requires an Authorization=Bearer%20... header; values omitted")
    return headers


def setup_telemetry():
    global _providers
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or _providers is not None:
        return _providers
    # Validate before SDK construction: its default parser logs malformed header values.
    headers = export_headers()
    resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "detour-api"),
        "service.version": os.getenv("APP_VERSION", "local"), "deployment.environment.name": "hackathon-demo"})
    traces = TracerProvider(resource=resource)
    traces.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(timeout=5, headers=headers), schedule_delay_millis=1000))
    trace.set_tracer_provider(traces)
    metric_provider = MeterProvider(resource=resource, metric_readers=[
        PeriodicExportingMetricReader(OTLPMetricExporter(timeout=5, headers=headers), export_interval_millis=15000)])
    metrics.set_meter_provider(metric_provider)
    logs = LoggerProvider(resource=resource)
    logs.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(timeout=5, headers=headers), schedule_delay_millis=1000))
    set_logger_provider(logs)
    logger.setLevel(logging.INFO)
    logger.addHandler(LoggingHandler(level=logging.INFO, logger_provider=logs))
    _providers = (traces, metric_provider, logs)
    return _providers


def flush_telemetry():
    return all(provider.force_flush() is not False for provider in (_providers or []))


async def instrument_request(request, call_next):
    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    started = perf_counter()
    with tracer.start_as_current_span("HTTP request", context=extract(request.headers), kind=SpanKind.SERVER,
                                     record_exception=False, set_status_on_exception=False) as span:
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            if span.get_span_context().is_valid:
                response.headers["X-Trace-Id"] = format(span.get_span_context().trace_id, "032x")
            return response
        finally:
            # Use route templates only; arbitrary URLs, queries and attendee tokens never enter telemetry.
            route = getattr(request.scope.get("route"), "path", "unmatched")
            attributes = {"http.request.method": request.method, "http.route": route, "http.response.status_code": status}
            span.update_name(f"{request.method} {route}")
            span.set_attributes(attributes)
            if status >= 500:
                span.set_status(StatusCode.ERROR)
            elapsed = perf_counter() - started
            request_duration.record(elapsed, attributes)
            logger.info("API request completed", extra={"http_method": request.method, "http_route": route,
                "http_status": status, "duration_ms": round(elapsed * 1000, 2),
                "trace_id": format(span.get_span_context().trace_id, "032x")})
