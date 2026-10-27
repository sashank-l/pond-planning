"""API routes with OpenTelemetry distributed tracing and metrics."""

from __future__ import annotations

import time
import json
import logging
import tempfile
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Response
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.parser.kml_parser import parse_upload
from app.dem.builder import build_dem
from app.terrain.analysis import analyze_terrain
from app.pond.selector import select_pond_and_delineate
from app.telemetry.tracer import get_tracer, trace_stage
from app.telemetry.metrics import get_metrics

logger = logging.getLogger("pond.api.routes")
router = APIRouter()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class PondSiteSchema(BaseModel):
    lat: float
    lon: float
    elevation_m: float
    flow_accumulation_cells: int


class CatchmentSchema(BaseModel):
    area_m2: float
    area_hectares: float
    mean_slope_pct: float
    max_slope_pct: float
    min_elevation_m: float
    max_elevation_m: float
    relief_m: float
    watershed_cell_count: int
    annual_rainfall_mm: float
    runoff_coefficient: float
    expected_water_volume_m3: float
    expected_water_volume_liters: float
    recommended_pond_depth_m: float
    recommended_pond_surface_area_m2: float
    recommended_storage_capacity_m3: float
    boundary_geojson: dict


class AnalyzeContourResponse(BaseModel):
    contour_interval_m: float
    elevation_range_m: list[float] = Field(..., min_length=2, max_length=2)
    total_contour_lines: int
    grid_resolution_m: float
    grid_shape: list[int] = Field(..., min_length=2, max_length=2)
    resolution_auto_adjusted: bool
    pond_site: PondSiteSchema
    catchment: CatchmentSchema
    processing_time_ms: float
    trace_id: str | None = Field(default=None, description="OpenTelemetry 32-hex Trace ID")
    span_id: str | None = Field(default=None, description="OpenTelemetry 16-hex Span ID")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/health")
async def health():
    return {"status": "ok", "service": "pond-planning-service", "telemetry": "active"}


@router.get("/sampleKml")
async def get_sample_kml():
    """Download the preloaded sample 1m contour KML file."""
    sample_path = Path(__file__).resolve().parent.parent.parent / "contours_1m.kml"
    if not sample_path.exists():
        raise HTTPException(status_code=404, detail="Sample contour file not found.")
    return FileResponse(
        str(sample_path),
        media_type="application/vnd.google-earth.kml+xml",
        filename="contours_1m.kml",
    )


@router.post("/analyzeContour", response_model=AnalyzeContourResponse)
async def analyze_contour(
    response: Response,
    file: UploadFile = File(..., description="KML or KMZ contour map"),
    resolution_m: float = Form(20.0, description="Grid resolution in metres", gt=0),
    min_catchment_area_m2: float = Form(
        500.0, description="Minimum catchment area in m²", gt=0
    ),
):
    t0 = time.perf_counter()
    tracer = get_tracer()
    metrics = get_metrics()

    filename = file.filename or "upload.kml"
    ext = Path(filename).suffix.lower()

    if ext not in {".kml", ".kmz"}:
        metrics.record_analysis_error(status="invalid_format", resolution_m=resolution_m)
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type {ext!r}. Upload a .kml or .kmz file.",
        )

    # --- Root OpenTelemetry Span ---
    with tracer.start_as_current_span(
        "pond.analyze_contour",
        attributes={
            "http.route": "/analyzeContour",
            "file.name": filename,
            "file.extension": ext,
            "analysis.resolution_m": resolution_m,
            "analysis.min_catchment_area_m2": min_catchment_area_m2,
        },
    ) as root_span:
        span_ctx = root_span.get_span_context()
        trace_id_str = format(span_ctx.trace_id, "032x") if span_ctx else "0" * 32
        span_id_str = format(span_ctx.span_id, "016x") if span_ctx else "0" * 16

        response.headers["X-Trace-Id"] = trace_id_str
        response.headers["X-Span-Id"] = span_id_str

        # Stage 1: Parse upload
        t_stage = time.perf_counter()
        with trace_stage("kml.parse", {"kml.filename": filename}) as span_parse:
            try:
                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                    content = await file.read()
                    tmp.write(content)

                span_parse.set_attribute("kml.bytes", len(content))

                with open(tmp_path, "rb") as fh:
                    dataset = parse_upload(fh, filename)

                tmp_path.unlink(missing_ok=True)

            except ValueError as exc:
                metrics.record_analysis_error(status="parse_error", resolution_m=resolution_m)
                logger.error("Failed to parse contour file: %s", exc)
                raise HTTPException(status_code=400, detail=str(exc))
            except Exception as exc:
                metrics.record_analysis_error(status="parse_error", resolution_m=resolution_m)
                logger.error("Unexpected error during parsing: %s", exc)
                raise HTTPException(status_code=400, detail=f"Failed to parse file: {exc}")

            if not dataset.contours:
                metrics.record_analysis_error(status="empty_contours", resolution_m=resolution_m)
                raise HTTPException(
                    status_code=400,
                    detail="No contour lines found in the uploaded file.",
                )

            span_parse.set_attribute("contour.lines_count", len(dataset.contours))
            span_parse.set_attribute("contour.elevation_min_m", round(dataset.elevation_min, 2))
            span_parse.set_attribute("contour.elevation_max_m", round(dataset.elevation_max, 2))
            span_parse.set_attribute("contour.interval_m", round(dataset.contour_interval, 2))
            span_parse.add_event("contours_parsed", {"count": len(dataset.contours)})

            d_parse = time.perf_counter() - t_stage
            metrics.record_stage("parse_kml", d_parse)
            logger.info("Parsed %d contour lines in %.2f ms", len(dataset.contours), d_parse * 1000)

        # Stage 2: Build DEM
        t_stage = time.perf_counter()
        with trace_stage("dem.build", {"dem.resolution_requested_m": resolution_m}) as span_dem:
            try:
                dem_result = build_dem(dataset, resolution_m=resolution_m)
            except Exception as exc:
                metrics.record_analysis_error(status="dem_build_failed", resolution_m=resolution_m)
                logger.error("DEM building failed: %s", exc)
                raise HTTPException(status_code=500, detail=f"DEM building failed: {exc}")

            total_cells = dem_result.rows * dem_result.cols
            span_dem.set_attribute("dem.rows", dem_result.rows)
            span_dem.set_attribute("dem.cols", dem_result.cols)
            span_dem.set_attribute("dem.total_cells", total_cells)
            span_dem.set_attribute("dem.effective_resolution_m", dem_result.resolution_m)
            span_dem.set_attribute("dem.auto_adjusted", dem_result.resolution_auto_adjusted)
            span_dem.add_event("dem_grid_ready", {"grid_shape": f"{dem_result.rows}x{dem_result.cols}"})

            d_dem = time.perf_counter() - t_stage
            metrics.record_stage("build_dem", d_dem)
            logger.info("Built DEM grid %dx%d (%d cells) in %.2f ms", dem_result.rows, dem_result.cols, total_cells, d_dem * 1000)

        # Stage 3: Terrain analysis
        t_stage = time.perf_counter()
        with trace_stage("terrain.analyze") as span_terrain:
            try:
                terrain = analyze_terrain(dem_result.elevation, dem_result.resolution_m)
            except Exception as exc:
                metrics.record_analysis_error(status="terrain_analysis_failed", resolution_m=resolution_m)
                logger.error("Terrain analysis failed: %s", exc)
                raise HTTPException(status_code=500, detail=f"Terrain analysis failed: {exc}")

            span_terrain.set_attribute("terrain.max_slope_pct", round(float(terrain.slope.max()), 2))
            span_terrain.set_attribute("terrain.max_flow_accumulation", int(terrain.flow_acc.max()))
            span_terrain.add_event("terrain_analyzed")

            d_terrain = time.perf_counter() - t_stage
            metrics.record_stage("terrain_analysis", d_terrain)
            logger.info("Terrain analysis finished in %.2f ms", d_terrain * 1000)

        # Stage 4: Pond site selection & catchment delineation
        t_stage = time.perf_counter()
        with trace_stage("pond.select_and_delineate", {"min_catchment_m2": min_catchment_area_m2}) as span_pond:
            try:
                catchment = select_pond_and_delineate(
                    dem_result,
                    terrain,
                    min_catchment_area_m2=min_catchment_area_m2,
                )
            except ValueError as exc:
                metrics.record_analysis_error(status="no_viable_site", resolution_m=resolution_m)
                logger.warning("No viable pond site: %s", exc)
                raise HTTPException(status_code=422, detail=str(exc))
            except Exception as exc:
                metrics.record_analysis_error(status="pond_selection_failed", resolution_m=resolution_m)
                logger.error("Pond site selection failed: %s", exc)
                raise HTTPException(status_code=500, detail=f"Pond site selection failed: {exc}")

            # Record detailed span attributes
            span_pond.set_attribute("pond.lat", catchment.pond_site.lat)
            span_pond.set_attribute("pond.lon", catchment.pond_site.lon)
            span_pond.set_attribute("pond.elevation_m", catchment.pond_site.elevation_m)
            span_pond.set_attribute("pond.flow_accumulation_cells", catchment.pond_site.flow_accumulation_cells)
            span_pond.set_attribute("catchment.area_m2", catchment.area_m2)
            span_pond.set_attribute("catchment.area_ha", catchment.area_hectares)
            span_pond.set_attribute("catchment.mean_slope_pct", catchment.mean_slope_pct)
            span_pond.set_attribute("catchment.relief_m", catchment.relief_m)
            span_pond.set_attribute("water.expected_volume_m3", catchment.expected_water_volume_m3)
            span_pond.set_attribute("water.expected_volume_liters", catchment.expected_water_volume_liters)
            span_pond.set_attribute("pond.recommended_depth_m", catchment.recommended_pond_depth_m)
            span_pond.set_attribute("pond.recommended_surface_area_m2", catchment.recommended_pond_surface_area_m2)
            span_pond.add_event("pond_catchment_selected")

            d_pond = time.perf_counter() - t_stage
            metrics.record_stage("pond_selection", d_pond)
            logger.info(
                "Pond selected at (%.6f, %.6f) elev=%.2fm, area=%.2f ha, volume=%.2f m3",
                catchment.pond_site.lat,
                catchment.pond_site.lon,
                catchment.pond_site.elevation_m,
                catchment.area_hectares,
                catchment.expected_water_volume_m3,
            )

        elapsed_sec = time.perf_counter() - t0
        elapsed_ms = elapsed_sec * 1000

        # Record metrics
        metrics.record_analysis_success(
            duration_sec=elapsed_sec,
            resolution_m=dem_result.resolution_m,
            contour_count=len(dataset.contours),
            grid_cells=dem_result.rows * dem_result.cols,
            relief_m=catchment.relief_m,
            catchment_area_m2=catchment.area_m2,
            water_volume_m3=catchment.expected_water_volume_m3,
            pond_depth_m=catchment.recommended_pond_depth_m,
        )

        root_span.set_attribute("analysis.total_duration_ms", round(elapsed_ms, 2))
        root_span.set_status(Status(StatusCode.OK))

        return AnalyzeContourResponse(
            contour_interval_m=round(dataset.contour_interval, 3),
            elevation_range_m=[
                round(dataset.elevation_min, 2),
                round(dataset.elevation_max, 2),
            ],
            total_contour_lines=len(dataset.contours),
            grid_resolution_m=dem_result.resolution_m,
            grid_shape=[dem_result.rows, dem_result.cols],
            resolution_auto_adjusted=dem_result.resolution_auto_adjusted,
            pond_site=PondSiteSchema(
                lat=catchment.pond_site.lat,
                lon=catchment.pond_site.lon,
                elevation_m=catchment.pond_site.elevation_m,
                flow_accumulation_cells=catchment.pond_site.flow_accumulation_cells,
            ),
            catchment=CatchmentSchema(
                area_m2=catchment.area_m2,
                area_hectares=catchment.area_hectares,
                mean_slope_pct=catchment.mean_slope_pct,
                max_slope_pct=catchment.max_slope_pct,
                min_elevation_m=catchment.min_elevation_m,
                max_elevation_m=catchment.max_elevation_m,
                relief_m=catchment.relief_m,
                watershed_cell_count=catchment.watershed_cell_count,
                annual_rainfall_mm=catchment.annual_rainfall_mm,
                runoff_coefficient=catchment.runoff_coefficient,
                expected_water_volume_m3=catchment.expected_water_volume_m3,
                expected_water_volume_liters=catchment.expected_water_volume_liters,
                recommended_pond_depth_m=catchment.recommended_pond_depth_m,
                recommended_pond_surface_area_m2=catchment.recommended_pond_surface_area_m2,
                recommended_storage_capacity_m3=catchment.recommended_storage_capacity_m3,
                boundary_geojson=catchment.boundary_geojson,
            ),
            processing_time_ms=round(elapsed_ms, 1),
            trace_id=trace_id_str,
            span_id=span_id_str,
        )


# ---------------------------------------------------------------------------
# Telemetry Inspection Endpoints (For Inspection and Dashboard)
# ---------------------------------------------------------------------------

@router.get("/telemetry/spans", summary="Get recent OpenTelemetry spans")
async def get_recent_spans(limit: int = 50):
    """Returns the most recent recorded OpenTelemetry spans as JSON."""
    logs_dir = Path("/home/student/pond_panning/logs")
    if not logs_dir.exists():
        logs_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    spans_file = logs_dir / "otel_spans.jsonl"

    if not spans_file.exists():
        return {"spans": [], "count": 0}

    spans = []
    try:
        with open(spans_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in reversed(lines[-limit:]):
                line = line.strip()
                if line:
                    spans.append(json.loads(line))
    except Exception as exc:
        logger.warning("Failed to read spans: %s", exc)

    return {"spans": spans, "count": len(spans)}


@router.get("/telemetry/overview", summary="Telemetry Overview and Status")
async def get_telemetry_overview():
    """Returns an overview of the OpenTelemetry pipeline status."""
    return {
        "service_name": "pond-planning-service",
        "version": "2.0.0",
        "status": "active",
        "otlp_endpoint": "http://127.0.0.1:4318/v1/traces",
        "jaeger_ui_port": 5209,
        "prometheus_metrics_endpoint": "/metrics",
        "spans_endpoint": "/telemetry/spans",
        "host": "stu3_sys1",
    }
