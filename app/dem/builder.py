"""DEM builder: reproject contour lines to local UTM, rasterize, and interpolate.

Key design decisions (see IMPLEMENTATION_PLAN.md §3):
- resolution_m is a required config knob.
- Auto-coarsening guard rail: if grid would exceed MAX_CELLS, resolution is
  increased until it fits, and `resolution_auto_adjusted` is set True.
- Uses scipy.interpolate.griddata (linear) — no GDAL dependency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from pyproj import Transformer
from scipy.interpolate import griddata

from app.parser.kml_parser import ContourDataset

# Guard rail: maximum number of grid cells we'll allow.
# At 512 MB RAM budget, ~86k cells is safe; allow up to 500k for laptop dev.
MAX_CELLS = 500_000


@dataclass
class DEMResult:
    elevation: np.ndarray          # 2-D float32 array, shape (rows, cols)
    x_min: float                    # UTM easting of left edge (m)
    y_min: float                    # UTM northing of bottom edge (m)
    resolution_m: float             # actual resolution used
    resolution_auto_adjusted: bool  # True if coarsened from requested value
    epsg: int                       # UTM zone EPSG

    @property
    def rows(self) -> int:
        return self.elevation.shape[0]

    @property
    def cols(self) -> int:
        return self.elevation.shape[1]

    def cell_to_utm(self, row: int, col: int) -> tuple[float, float]:
        """Return (easting, northing) of the centre of cell (row, col)."""
        x = self.x_min + (col + 0.5) * self.resolution_m
        y = self.y_min + (self.rows - 1 - row + 0.5) * self.resolution_m
        return x, y

    def utm_to_lonlat(self, easting: float, northing: float) -> tuple[float, float]:
        t = Transformer.from_crs(f"EPSG:{self.epsg}", "EPSG:4326", always_xy=True)
        lon, lat = t.transform(easting, northing)
        return lon, lat


def _best_utm_epsg(lon: float, lat: float) -> int:
    """Return EPSG code for the UTM zone containing (lon, lat)."""
    zone = math.floor((lon + 180) / 6) + 1
    if lat >= 0:
        return 32600 + zone   # Northern hemisphere
    else:
        return 32700 + zone   # Southern hemisphere


def build_dem(
    dataset: ContourDataset,
    resolution_m: float = 10.0,
    max_cells: int = MAX_CELLS,
) -> DEMResult:
    """
    Reproject contour lines to local UTM, rasterize, and interpolate a DEM.

    Parameters
    ----------
    dataset:      parsed ContourDataset (lon/lat WGS84)
    resolution_m: desired grid resolution in metres
    max_cells:    guard-rail ceiling on total grid cells

    Returns
    -------
    DEMResult containing a 2-D float32 elevation array and metadata.
    """
    if not dataset.contours:
        raise ValueError("ContourDataset is empty — no contour lines to process")

    # ---- 1. Find centroid for UTM zone selection ----
    all_lons = [pt[0] for c in dataset.contours for pt in c.points]
    all_lats = [pt[1] for c in dataset.contours for pt in c.points]
    centre_lon = (min(all_lons) + max(all_lons)) / 2
    centre_lat = (min(all_lats) + max(all_lats)) / 2
    epsg = _best_utm_epsg(centre_lon, centre_lat)

    # ---- 2. Reproject all points to UTM ----
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    xs_utm: list[float] = []
    ys_utm: list[float] = []
    elevs: list[float] = []

    for contour in dataset.contours:
        for lon, lat in contour.points:
            ex, ey = transformer.transform(lon, lat)
            xs_utm.append(ex)
            ys_utm.append(ey)
            elevs.append(contour.elevation)

    xs = np.array(xs_utm, dtype=np.float64)
    ys = np.array(ys_utm, dtype=np.float64)
    zs = np.array(elevs, dtype=np.float64)

    x_min, x_max = xs.min(), xs.max()
    y_min, y_max = ys.min(), ys.max()
    width_m  = x_max - x_min
    height_m = y_max - y_min

    # ---- 3. Auto-coarsen guard rail ----
    resolution_auto_adjusted = False
    while True:
        cols = max(2, int(math.ceil(width_m  / resolution_m)))
        rows = max(2, int(math.ceil(height_m / resolution_m)))
        if rows * cols <= max_cells:
            break
        resolution_m *= math.sqrt(rows * cols / max_cells)
        resolution_m = math.ceil(resolution_m)  # round up to integer metres
        resolution_auto_adjusted = True

    # ---- 4. Build target grid ----
    xi = np.linspace(x_min, x_max, cols)
    yi = np.linspace(y_min, y_max, rows)
    grid_x, grid_y = np.meshgrid(xi, yi)

    # griddata expects (n, 2) points array
    points_2d = np.column_stack([xs, ys])

    # Interpolate — linear is fast and well-behaved within the convex hull
    dem = griddata(points_2d, zs, (grid_x, grid_y), method="linear")

    # Fill any NaN edge cells (outside convex hull) with nearest neighbour
    if np.isnan(dem).any():
        dem_nearest = griddata(points_2d, zs, (grid_x, grid_y), method="nearest")
        nan_mask = np.isnan(dem)
        dem[nan_mask] = dem_nearest[nan_mask]

    # Flip so row 0 = top (north), matching raster convention
    dem = np.flipud(dem).astype(np.float32)

    return DEMResult(
        elevation=dem,
        x_min=x_min,
        y_min=y_min,
        resolution_m=float(resolution_m),
        resolution_auto_adjusted=resolution_auto_adjusted,
        epsg=epsg,
    )
