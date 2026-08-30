"""API routes: POST /analyzeContour and GET /health."""

from __future__ import annotations

import time
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.parser.kml_parser import parse_upload
from app.dem.builder import build_dem
from app.terrain.analysis import analyze_terrain
from app.pond.selector import select_pond_and_delineate

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class PondSiteSchema(BaseModel):
    lat: float
    lon: float
    elevation_m: float


class CatchmentSchema(BaseModel):
    area_m2: float
    area_hectares: float
    mean_slope_pct: float
    boundary_geojson: dict


class AnalyzeContourResponse(BaseModel):
    contour_interval_m: float
    elevation_range_m: list[float] = Field(..., min_length=2, max_length=2)
    grid_resolution_m: float
    resolution_auto_adjusted: bool
    pond_site: PondSiteSchema
    catchment: CatchmentSchema
    processing_time_ms: float


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/analyzeContour", response_model=AnalyzeContourResponse)
async def analyze_contour(
    file: UploadFile = File(..., description="KML or KMZ contour map"),
    resolution_m: float = Form(10.0, description="Grid resolution in metres", gt=0),
    min_catchment_area_m2: float = Form(
        500.0, description="Minimum catchment area in m²", gt=0
    ),
):
    t0 = time.perf_counter()
    filename = file.filename or "upload.kml"
    ext = Path(filename).suffix.lower()

    if ext not in {".kml", ".kmz"}:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type {ext!r}. Upload a .kml or .kmz file.",
        )

    # --- Parse ---
    try:
        # Write to a temp file to avoid buffering huge uploads in RAM
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp_path = Path(tmp.name)
            content = await file.read()
            tmp.write(content)

        with open(tmp_path, "rb") as fh:
            dataset = parse_upload(fh, filename)

        tmp_path.unlink(missing_ok=True)

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {exc}")

    if not dataset.contours:
        raise HTTPException(
            status_code=400,
            detail="No contour lines found in the uploaded file.",
        )

    # --- Build DEM ---
    try:
        dem_result = build_dem(dataset, resolution_m=resolution_m)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DEM building failed: {exc}")

    # --- Terrain analysis ---
    try:
        terrain = analyze_terrain(dem_result.elevation, dem_result.resolution_m)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Terrain analysis failed: {exc}")

    # --- Pond site + catchment ---
    try:
        catchment = select_pond_and_delineate(
            dem_result,
            terrain,
            min_catchment_area_m2=min_catchment_area_m2,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pond site selection failed: {exc}")

    elapsed_ms = (time.perf_counter() - t0) * 1000

    return AnalyzeContourResponse(
        contour_interval_m=round(dataset.contour_interval, 3),
        elevation_range_m=[
            round(dataset.elevation_min, 2),
            round(dataset.elevation_max, 2),
        ],
        grid_resolution_m=dem_result.resolution_m,
        resolution_auto_adjusted=dem_result.resolution_auto_adjusted,
        pond_site=PondSiteSchema(
            lat=catchment.pond_site.lat,
            lon=catchment.pond_site.lon,
            elevation_m=catchment.pond_site.elevation_m,
        ),
        catchment=CatchmentSchema(
            area_m2=catchment.area_m2,
            area_hectares=catchment.area_hectares,
            mean_slope_pct=catchment.mean_slope_pct,
            boundary_geojson=catchment.boundary_geojson,
        ),
        processing_time_ms=round(elapsed_ms, 1),
    )
