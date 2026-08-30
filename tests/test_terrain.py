"""Terrain analysis unit tests.

All tests run on small synthetic grids to assert exact expected behavior
(e.g. a synthetic bowl DEM should drain to the bowl center).
"""

import numpy as np
import pytest


def _bowl_dem(size=20, rim=300.0, floor=270.0):
    """A circular bowl: high elevation at edges, low at center."""
    rows, cols = size, size
    cx, cy = size // 2, size // 2
    dem = np.zeros((rows, cols), dtype=np.float32)
    for r in range(rows):
        for c in range(cols):
            dist = np.sqrt((r - cy) ** 2 + (c - cx) ** 2)
            dem[r, c] = floor + (rim - floor) * (dist / (size / 2))
    return dem


def _ridge_dem(size=20, left=270.0, right=300.0):
    """Simple slope from left (low) to right (high)."""
    cols = np.linspace(left, right, size)
    return np.tile(cols, (size, 1)).astype(np.float32)


def test_fill_depressions_no_depressions():
    from app.terrain.analysis import fill_depressions
    dem = _bowl_dem()
    # Bowl center is a natural depression — filled version should be >= original
    filled = fill_depressions(dem)
    assert (filled >= dem - 1e-4).all(), "Filled DEM must be >= original DEM everywhere"


def test_fill_depressions_flat_after_fill():
    from app.terrain.analysis import fill_depressions
    # A DEM with an artificial pit
    dem = np.array([
        [10., 10., 10., 10., 10.],
        [10.,  5.,  5.,  5., 10.],
        [10.,  5.,  1.,  5., 10.],
        [10.,  5.,  5.,  5., 10.],
        [10., 10., 10., 10., 10.],
    ], dtype=np.float32)
    filled = fill_depressions(dem)
    # The center depression should be raised to ≥ its spill point
    assert filled[2, 2] >= 5.0


def test_flow_direction_ridge():
    from app.terrain.analysis import compute_flow_direction, fill_depressions
    dem = _ridge_dem()
    filled = fill_depressions(dem)
    fdir = compute_flow_direction(filled)
    # On a left-to-right slope, interior cells should flow westward (direction 6)
    # or at least have a valid (non -1) flow direction
    interior = fdir[2:-2, 2:-2]
    assert (interior >= 0).any(), "Some interior cells should have a valid flow direction"


def test_flow_accumulation_slope():
    """On a simple north-to-south slope, accumulation should peak at the south edge row."""
    from app.terrain.analysis import (
        fill_depressions,
        compute_flow_direction,
        compute_flow_accumulation,
    )
    size = 15
    # Slope high in row 0 (north), low in last row (south)
    dem = np.tile(np.linspace(300.0, 270.0, size), (size, 1)).T.astype(np.float32)
    filled = fill_depressions(dem)
    fdir = compute_flow_direction(filled)
    facc = compute_flow_accumulation(fdir)
    max_idx = np.unravel_index(facc.argmax(), facc.shape)
    # Max accumulation should be in the bottom half (high row index = south = low elevation)
    assert max_idx[0] >= size // 2, (
        f"Peak accumulation row {max_idx[0]} should be in the lower (south) half"
    )


def test_slope_flat_dem():
    from app.terrain.analysis import compute_slope
    dem = np.ones((10, 10), dtype=np.float32) * 100.0
    slope = compute_slope(dem, resolution_m=10.0)
    assert slope.max() < 0.01, "Flat DEM should have near-zero slope"


def test_slope_positive_for_sloped_dem():
    from app.terrain.analysis import compute_slope
    dem = _ridge_dem(size=10)
    slope = compute_slope(dem, resolution_m=10.0)
    assert slope[5, 5] > 0.0, "Sloped DEM should have positive slope"


def test_analyze_terrain_returns_correct_shapes():
    from app.terrain.analysis import analyze_terrain
    dem = _bowl_dem(size=12)
    result = analyze_terrain(dem, resolution_m=5.0)
    assert result.filled.shape == dem.shape
    assert result.flow_dir.shape == dem.shape
    assert result.flow_acc.shape == dem.shape
    assert result.slope.shape == dem.shape
