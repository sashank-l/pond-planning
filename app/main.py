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

BACKEND_GATEWAY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Backend API & Observability Gateway | Village Pond Planning</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" />
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card: #0f172a;
      --border: rgba(255, 255, 255, 0.1);
      --primary: #38bdf8;
      --accent: #06b6d4;
      --success: #22c55e;
      --text: #f8fafc;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      padding: 24px;
    }
    .container {
      max-width: 860px;
      width: 100%;
    }
    .header {
      text-align: center;
      margin-bottom: 36px;
    }
    .header h1 {
      font-size: 26px;
      font-weight: 700;
      letter-spacing: -0.5px;
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
    }
    .header h1 i { color: var(--primary); }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 12px;
      border-radius: 999px;
      background: rgba(34, 197, 94, 0.15);
      border: 1px solid rgba(34, 197, 94, 0.3);
      color: var(--success);
      font-size: 12px;
      font-weight: 600;
    }
    .header p {
      color: var(--text-muted);
      margin-top: 12px;
      font-size: 14px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 20px;
      margin-bottom: 32px;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 24px;
      text-decoration: none;
      color: inherit;
      display: flex;
      flex-direction: column;
      transition: all 0.25s ease;
    }
    .card:hover {
      border-color: var(--primary);
      transform: translateY(-3px);
      box-shadow: 0 12px 24px -10px rgba(56, 189, 248, 0.25);
    }
    .card-icon {
      font-size: 28px;
      margin-bottom: 16px;
    }
    .card-title {
      font-size: 16px;
      font-weight: 700;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .card-title i { font-size: 14px; color: var(--text-muted); }
    .card-desc {
      font-size: 13px;
      color: var(--text-muted);
      line-height: 1.5;
      margin-bottom: 16px;
      flex: 1;
    }
    .card-endpoint {
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      background: rgba(255, 255, 255, 0.05);
      padding: 6px 10px;
      border-radius: 6px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      color: var(--primary);
      word-break: break-all;
    }
    .footer {
      text-align: center;
      font-size: 12px;
      color: var(--text-muted);
      border-top: 1px solid var(--border);
      padding-top: 20px;
    }
    .footer code {
      font-family: 'JetBrains Mono', monospace;
      color: var(--primary);
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="badge"><i class="fa-solid fa-circle-check"></i> System Online &bull; Container: stu3_sys1</div>
      <h1 style="margin-top:16px;"><i class="fa-solid fa-server"></i> Village Pond Planning Backend</h1>
      <p>Civil Hydrology Analysis Engine &bull; OpenTelemetry Observability Gateway &bull; Port 3209</p>
    </div>

    <div class="grid">
      <a href="/telemetry" class="card" style="border-color: rgba(56, 189, 248, 0.4);">
        <div class="card-icon" style="color: #38bdf8;"><i class="fa-solid fa-chart-line"></i></div>
        <div class="card-title">OpenTelemetry Dashboard <i class="fa-solid fa-arrow-up-right-from-square"></i></div>
        <div class="card-desc">Interactive trace waterfall, stage execution breakdown, and correlated structured logs.</div>
        <div class="card-endpoint">GET /telemetry</div>
      </a>

      <a href="/metrics" class="card">
        <div class="card-icon" style="color: #22c55e;"><i class="fa-solid fa-gauge-high"></i></div>
        <div class="card-title">Prometheus Metrics <i class="fa-solid fa-arrow-up-right-from-square"></i></div>
        <div class="card-desc">Standard Prometheus pull metrics endpoint tracking request rates, durations, and hydrology gauges.</div>
        <div class="card-endpoint">GET /metrics</div>
      </a>

      <a href="/docs" class="card">
        <div class="card-icon" style="color: #f59e0b;"><i class="fa-solid fa-book-open"></i></div>
        <div class="card-title">Swagger API Docs <i class="fa-solid fa-arrow-up-right-from-square"></i></div>
        <div class="card-desc">Interactive OpenAPI documentation for testing /analyzeContour and JSON telemetry endpoints.</div>
        <div class="card-endpoint">GET /docs</div>
      </a>

      <a href="http://10.1.75.51:4209/" class="card" target="_blank">
        <div class="card-icon" style="color: #06b6d4;"><i class="fa-solid fa-map-location-dot"></i></div>
        <div class="card-title">GIS Map Frontend <i class="fa-solid fa-arrow-up-right-from-square"></i></div>
        <div class="card-desc">Satellite contour map UI with interactive pond delineation, catchment rendering, and GeoJSON export.</div>
        <div class="card-endpoint">http://10.1.75.51:4209/</div>
      </a>
    </div>

    <div class="footer">
      Python 3.12 &bull; FastAPI 0.115 &bull; OpenTelemetry SDK 1.45.1 &bull; Container: <code>stu3_sys1 (10.1.75.51)</code>
    </div>
  </div>
</body>
</html>
"""

# 8. Mount Backend Gateway at root
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_backend_gateway():
    """Serves the Backend Gateway portal distinguishing port 3209 from port 4209."""
    return HTMLResponse(content=BACKEND_GATEWAY_HTML)
