"""DEM builder unit tests.

Uses the real sample KML and a tiny synthetic dataset.
"""

import numpy as np
import pytest
from pathlib import Path

SAMPLE_KML = Path(__file__).parent.parent / "contours_1m.kml"


def _make_synthetic_dataset():
    """A tiny 3-contour dataset spanning ~1km × 1km in UTM zone 44N."""
    from app.parser.kml_parser import ContourDataset, ContourLine

    # Three contour lines at 100m, 110m, 120m elevation
    # around a fake location in central India (~lon 81, lat 21)
    base_lon, base_lat = 81.0, 21.0
    contours = [
        ContourLine(elevation=100.0, points=[
            (base_lon,       base_lat),
            (base_lon+0.01,  base_lat),
            (base_lon+0.01,  base_lat+0.01),
            (base_lon,       base_lat+0.01),
        ]),
        ContourLine(elevation=110.0, points=[
            (base_lon+0.003, base_lat+0.003),
            (base_lon+0.007, base_lat+0.003),
            (base_lon+0.007, base_lat+0.007),
            (base_lon+0.003, base_lat+0.007),
        ]),
        ContourLine(elevation=120.0, points=[
            (base_lon+0.004, base_lat+0.004),
            (base_lon+0.006, base_lat+0.004),
            (base_lon+0.006, base_lat+0.006),
        ]),
    ]
    return ContourDataset(contours=contours)


def test_build_dem_synthetic():
    from app.dem.builder import build_dem
    ds = _make_synthetic_dataset()
    result = build_dem(ds, resolution_m=50.0)
    assert result.elevation.ndim == 2
    assert result.elevation.shape[0] > 0
    assert result.elevation.shape[1] > 0
    assert not np.isnan(result.elevation).any(), "DEM should have no NaN after fill"
    assert result.resolution_m == pytest.approx(50.0, rel=0.01)
    assert result.resolution_auto_adjusted is False


def test_build_dem_auto_coarsen():
    """Force auto-coarsening by setting a very low cell ceiling."""
    from app.dem.builder import build_dem
    ds = _make_synthetic_dataset()
    result = build_dem(ds, resolution_m=1.0, max_cells=100)
    assert result.resolution_auto_adjusted is True
    assert result.rows * result.cols <= 100


def test_build_dem_elevation_range_plausible():
    from app.dem.builder import build_dem
    ds = _make_synthetic_dataset()
    result = build_dem(ds, resolution_m=50.0)
    assert result.elevation.min() >= 95.0
    assert result.elevation.max() <= 125.0


@pytest.mark.skipif(not SAMPLE_KML.exists(), reason="contours_1m.kml not present")
def test_build_dem_sample_kml():
    from app.parser.kml_parser import parse_file
    from app.dem.builder import build_dem
    ds = parse_file(SAMPLE_KML)
    result = build_dem(ds, resolution_m=20.0)
    assert result.elevation.shape[0] > 0
    assert result.elevation.shape[1] > 0
    assert not np.isnan(result.elevation).any()
    # Elevation range for contours_1m.kml is ~267–298 m; allow a modest margin
    assert result.elevation.min() > 260.0, f"Unexpected min elevation: {result.elevation.min()}"
    assert result.elevation.max() < 310.0, f"Unexpected max elevation: {result.elevation.max()}"
