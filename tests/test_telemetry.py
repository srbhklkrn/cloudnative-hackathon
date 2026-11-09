from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from backend import telemetry
from backend.main import create_app
import pytest


def test_http_telemetry_has_trace_correlation_without_search_or_cookie(monkeypatch, store):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "tracer", provider.get_tracer("test-http"))
    with TestClient(create_app(store)) as client:
        response = client.get("/api/search", params={"q": "private-search-phrase"},
                              cookies={"detour_attendee": "private-cookie"})
        assert response.status_code == 200
        spans = exporter.get_finished_spans()
        assert spans[-1].name == "GET /api/search"
        assert response.headers["x-trace-id"] == format(spans[-1].context.trace_id, "032x")
        assert "private-search-phrase" not in str(spans[-1].attributes)
        assert "private-cookie" not in str(spans[-1].attributes)
        assert spans[-1].attributes["http.response.status_code"] == 200
    provider.shutdown()


def test_invalid_header_cannot_leak_through_sdk_logging(monkeypatch, caplog):
    secret = "auth_example_private_value"
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", secret)
    with pytest.raises(ValueError) as error:
        telemetry.export_headers()
    assert secret not in str(error.value)
    assert secret not in caplog.text
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=Bearer%20" + secret)
    assert telemetry.export_headers()["Authorization"] == "Bearer " + secret
