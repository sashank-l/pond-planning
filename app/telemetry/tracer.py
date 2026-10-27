"""OpenTelemetry tracing setup and span helpers."""

from __future__ import annotations

import os
import json
import time
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Generator, Dict

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from opentelemetry.sdk.trace import TracerProvider, SpanProcessor, ReadableSpan
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

logger = logging.getLogger("pond.telemetry.tracer")

# Global tracer instance
_TRACER: trace.Tracer | None = None
_LOGS_DIR = Path("/home/student/pond_panning/logs")
if not _LOGS_DIR.exists():
    _LOGS_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
_LOGS_DIR.mkdir(parents=True, exist_ok=True)
_SPANS_FILE = _LOGS_DIR / "otel_spans.jsonl"


class FileJsonSpanExporter(SpanExporter):
    """Custom OpenTelemetry SpanExporter that records all spans to JSON Lines."""

    def __init__(self, file_path: Path):
        self.file_path = file_path

    def export(self, spans: list[ReadableSpan]) -> SpanExportResult:
        try:
            with open(self.file_path, "a", encoding="utf-8") as f:
                for span in spans:
                    ctx = span.get_span_context()
                    parent_ctx = span.parent
                    span_dict = {
                        "trace_id": format(ctx.trace_id, "032x"),
                        "span_id": format(ctx.span_id, "016x"),
                        "parent_span_id": format(parent_ctx.span_id, "016x") if parent_ctx else None,
                        "name": span.name,
                        "start_time_ns": span.start_time,
                        "end_time_ns": span.end_time,
                        "duration_ms": round((span.end_time - span.start_time) / 1e6, 2) if span.end_time else None,
                        "status": span.status.status_code.name,
                        "attributes": dict(span.attributes or {}),
                        "events": [
                            {
                                "name": event.name,
                                "timestamp_ns": event.timestamp,
                                "attributes": dict(event.attributes or {}),
                            }
                            for event in span.events
                        ],
                    }
                    f.write(json.dumps(span_dict) + "\n")
            return SpanExportResult.SUCCESS
        except Exception as exc:
            logger.warning("Failed to write span to file exporter: %s", exc)
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        pass


def init_tracer(service_name: str = "pond-planning-service") -> trace.Tracer:
    """Initialize OpenTelemetry tracer with OTLP and File exporters."""
    global _TRACER

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": "2.0.0",
            "deployment.environment": "production",
            "host.name": "stu3_sys1",
            "service.namespace": "civil-engineering.hydrology",
        }
    )

    provider = TracerProvider(resource=resource)

    # 1. OTLP HTTP Exporter to Jaeger/Collector (only if collector is running on port 4318)
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://127.0.0.1:4318/v1/traces")
    enable_otlp = os.getenv("ENABLE_OTLP_HTTP", "").lower() in ("true", "1", "yes")
    if not enable_otlp:
        try:
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                enable_otlp = (s.connect_ex(("127.0.0.1", 4318)) == 0)
        except Exception:
            enable_otlp = False

    if enable_otlp:
        try:
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, timeout=2)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter, max_queue_size=2048, schedule_delay_millis=500))
            logger.info("Configured OTLP HTTP span exporter -> %s", otlp_endpoint)
        except Exception as exc:
            logger.warning("Could not setup OTLP HTTP exporter: %s", exc)
    else:
        logger.info("OTLP receiver not detected on :4318; active span sink is FileJsonSpanExporter")

    # 2. File JSON Lines Exporter (persistent on disk for inspection)
    try:
        file_exporter = FileJsonSpanExporter(_SPANS_FILE)
        provider.add_span_processor(SimpleSpanProcessor(file_exporter))
        logger.info("Configured File JSON span exporter -> %s", _SPANS_FILE)
    except Exception as exc:
        logger.warning("Could not setup File span exporter: %s", exc)

    trace.set_tracer_provider(provider)
    _TRACER = trace.get_tracer(service_name, "2.0.0")
    return _TRACER


def get_tracer() -> trace.Tracer:
    """Get or initialize the global OpenTelemetry tracer."""
    global _TRACER
    if _TRACER is None:
        _TRACER = init_tracer()
    return _TRACER


@contextmanager
def trace_stage(
    stage_name: str,
    attributes: Dict[str, Any] | None = None,
) -> Generator[trace.Span, None, None]:
    """Context manager to instrument a sub-stage of processing with OpenTelemetry."""
    tracer = get_tracer()
    with tracer.start_as_current_span(stage_name) as span:
        if attributes:
            for k, v in attributes.items():
                if v is not None:
                    span.set_attribute(k, v)
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, description=str(exc)))
            raise
