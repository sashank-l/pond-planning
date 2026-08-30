"""Integration tests: full POST /analyzeContour pipeline against contours_1m.kml."""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app

SAMPLE_KML = Path(__file__).parent.parent / "contours_1m.kml"

pytestmark = pytest.mark.skipif(
    not SAMPLE_KML.exists(), reason="contours_1m.kml not present"
)

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_analyze_contour_sample_kml():
    with open(SAMPLE_KML, "rb") as f:
        resp = client.post(
            "/analyzeContour",
            files={"file": ("contours_1m.kml", f, "application/vnd.google-earth.kml+xml")},
            data={"resolution_m": "20.0", "min_catchment_area_m2": "500.0"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Response shape
    assert "pond_site" in body
    assert "catchment" in body
    assert "elevation_range_m" in body
    assert "contour_interval_m" in body
    assert "processing_time_ms" in body

    # Sanity: pond site coordinates should be in the plausible geographic area
    ps = body["pond_site"]
    assert isinstance(ps["lat"], float)
    assert isinstance(ps["lon"], float)
    assert ps["elevation_m"] > 0

    # Catchment stats
    catchment = body["catchment"]
    assert catchment["area_m2"] > 0
    assert catchment["area_hectares"] > 0
    assert catchment["boundary_geojson"]["type"] in {"Polygon", "MultiPolygon"}

    # Elevation range
    lo, hi = body["elevation_range_m"]
    assert lo < hi


def test_analyze_contour_invalid_format():
    resp = client.post(
        "/analyzeContour",
        files={"file": ("map.txt", b"garbage data", "text/plain")},
        data={"resolution_m": "10.0"},
    )
    assert resp.status_code == 400


def test_analyze_contour_corrupt_kml():
    resp = client.post(
        "/analyzeContour",
        files={"file": ("map.kml", b"<broken xml>", "application/vnd.google-earth.kml+xml")},
        data={"resolution_m": "10.0"},
    )
    assert resp.status_code in {400, 422}
