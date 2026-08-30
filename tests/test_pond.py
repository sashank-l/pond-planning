"""Pond site selection unit tests."""

import numpy as np
import pytest


def _make_bowl_dem_result(size=30, resolution_m=10.0):
    """Synthetic bowl DEM + DEMResult for pond selection tests."""
    from app.dem.builder import DEMResult

    # Bowl: low in center, high at edges
    cx, cy = size // 2, size // 2
    dem = np.zeros((size, size), dtype=np.float32)
    for r in range(size):
        for c in range(size):
            dist = np.sqrt((r - cy) ** 2 + (c - cx) ** 2)
            dem[r, c] = 270.0 + 30.0 * (dist / (size / 2))

    dem_result = DEMResult(
        elevation=dem,
        x_min=0.0,
        y_min=0.0,
        resolution_m=resolution_m,
        resolution_auto_adjusted=False,
        epsg=32644,  # UTM zone 44N
    )
    return dem_result


def test_select_pond_returns_valid_result():
    from app.terrain.analysis import analyze_terrain
    from app.pond.selector import select_pond_and_delineate

    dem_result = _make_bowl_dem_result(size=30)
    terrain = analyze_terrain(dem_result.elevation, dem_result.resolution_m)
    result = select_pond_and_delineate(
        dem_result, terrain, min_catchment_area_m2=100.0
    )
    assert result.area_m2 > 0
    assert result.area_hectares > 0
    assert result.mask.sum() > 0
    assert result.boundary_geojson["type"] in {"Polygon", "MultiPolygon"}


def test_pond_site_inside_grid():
    from app.terrain.analysis import analyze_terrain
    from app.pond.selector import select_pond_and_delineate

    size = 30
    dem_result = _make_bowl_dem_result(size=size)
    terrain = analyze_terrain(dem_result.elevation, dem_result.resolution_m)
    result = select_pond_and_delineate(
        dem_result, terrain, min_catchment_area_m2=100.0
    )
    ps = result.pond_site
    assert 0 <= ps.row < size
    assert 0 <= ps.col < size


def test_flat_terrain_raises():
    """Completely flat terrain should raise ValueError (no valid pond site)."""
    from app.dem.builder import DEMResult
    from app.terrain.analysis import analyze_terrain
    from app.pond.selector import select_pond_and_delineate

    dem = np.ones((20, 20), dtype=np.float32) * 270.0
    dem_result = DEMResult(
        elevation=dem, x_min=0.0, y_min=0.0,
        resolution_m=10.0, resolution_auto_adjusted=False, epsg=32644
    )
    terrain = analyze_terrain(dem, resolution_m=10.0)
    with pytest.raises(ValueError):
        select_pond_and_delineate(dem_result, terrain, min_catchment_area_m2=500.0)


def test_watershed_mask_covers_outlet():
    from app.terrain.analysis import analyze_terrain
    from app.pond.selector import select_pond_and_delineate

    dem_result = _make_bowl_dem_result(size=30)
    terrain = analyze_terrain(dem_result.elevation, dem_result.resolution_m)
    result = select_pond_and_delineate(
        dem_result, terrain, min_catchment_area_m2=100.0
    )
    ps = result.pond_site
    assert result.mask[ps.row, ps.col], "Outlet cell must be inside its own watershed mask"
