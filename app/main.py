"""FastAPI application entry point with OpenTelemetry and Prometheus instrumentation."""

from __future__ import annotations

import logging
from pathlib import Path
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
import json
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.api.routes import router
from app.telemetry.tracer import init_tracer
from app.telemetry.metrics import init_metrics, get_metrics
from app.telemetry.logging_setup import init_logging
from telemetry_server import HTML_DASHBOARD, SPANS_FILE, LOGS_FILE

logger = logging.getLogger("pond.main")

# 1. Initialize OpenTelemetry systems
init_logging()
init_tracer(service_name="pond-planning-service")
init_metrics()

# 2. FastAPI Application
app = FastAPI(
    title="Village Pond Planning System API",
    description=(
        "Upload a contour map (KML/KMZ), get back the ideal pond site, "
        "delineated catchment area, and expected water volume. "
        "Fully instrumented with OpenTelemetry traces, metrics, and structured logs."
    ),
    version="2.0.0",
)

# 3. Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# 4. OpenTelemetry Automatic FastAPI Instrumentation
try:
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=trace.get_tracer_provider(),
        excluded_urls="health,metrics,static,telemetry",
    )
    logger.info("OpenTelemetry FastAPI auto-instrumentation active")
except Exception as exc:
    logger.warning("FastAPI auto-instrumentation warning: %s", exc)

# 5. Prometheus Metrics Endpoint
@app.get("/metrics", summary="OpenTelemetry & Prometheus Metrics Endpoint")
async def prometheus_metrics():
    """Exposes real-time Prometheus metrics for scrapers and dashboards."""
    metrics_data = get_metrics().generate_prometheus_metrics()
    return Response(content=metrics_data, media_type="text/plain; version=0.0.4; charset=utf-8")


# 6. Interactive OpenTelemetry Observability Dashboard
@app.get("/telemetry", response_class=HTMLResponse, summary="OpenTelemetry Observability Dashboard")
@app.get("/dashboard", response_class=HTMLResponse, summary="OpenTelemetry Observability Dashboard")
async def serve_telemetry_dashboard():
    """Serves the interactive OpenTelemetry Web Dashboard."""
    return HTMLResponse(content=HTML_DASHBOARD)


@app.get("/api/spans", summary="Get trace spans for dashboard")
async def get_dashboard_spans():
    """Returns stored OpenTelemetry spans."""
    spans = []
    if SPANS_FILE.exists():
        try:
            with open(SPANS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        spans.append(json.loads(line))
        except Exception as exc:
            logger.error("Error reading spans file: %s", exc)
    return {"spans": spans[-100:], "count": len(spans)}


@app.get("/api/metrics", summary="Get Prometheus metrics for dashboard")
async def get_dashboard_metrics():
    """Returns Prometheus metrics formatted for dashboard visualizer."""
    metrics_data = get_metrics().generate_prometheus_metrics()
    return Response(content=metrics_data, media_type="text/plain; charset=utf-8")


@app.get("/api/logs", summary="Get correlated telemetry logs for dashboard")
async def get_dashboard_logs():
    """Returns recent structured logs with trace IDs."""
    logs = ""
    if LOGS_FILE.exists():
        try:
            with open(LOGS_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
                logs = "".join(lines[-150:])
        except Exception as exc:
            logger.error("Error reading logs file: %s", exc)
    return Response(content=logs, media_type="text/plain; charset=utf-8")


# 7. Include API router
app.include_router(router)

# 8. Mount frontend if it exists
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(str(frontend_dir / "index.html"))
