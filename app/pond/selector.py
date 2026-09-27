"""Pond site selection and catchment delineation.

Scoring heuristic
-----------------
Score = w_acc * norm(flow_acc) + w_dep * norm(depression_depth)
        - w_boundary * boundary_penalty

where:
  flow_acc       - higher means more upstream drainage
  depression_depth - (filled - original), positive in depressions/flats
  boundary_penalty - 1 if within border_cells of grid edge, else 0

The highest-scoring non-boundary cell above min_flow_acc is selected as
the pond outlet.

Watershed delineation
---------------------
From the outlet cell, trace upstream following the inverse of flow_dir —
collect every cell whose D8 drainage path eventually reaches the outlet.
BFS from outlet through cells that point to it.

Boundary polygon
----------------
Convert the raster watershed mask to a vector polygon via Shapely's
`unary_union` of per-cell bounding boxes, then simplify.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon, box, mapping
from shapely.ops import unary_union

from app.dem.builder import DEMResult
from app.terrain.analysis import D8_OFFSETS, TerrainResult


@dataclass
class PondSite:
    row: int
    col: int
    lat: float
    lon: float
    elevation_m: float
    flow_accumulation_cells: int


@dataclass
class CatchmentResult:
    pond_site: PondSite
    mask: np.ndarray          # bool 2-D watershed mask
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
    boundary_geojson: dict    # GeoJSON Polygon


def _build_upstream_map(
    flow_dir: np.ndarray,
) -> dict[tuple[int, int], list[tuple[int, int]]]:
    """Build inverse flow direction: cell → list of cells that drain into it."""
    rows, cols = flow_dir.shape
    upstream: dict[tuple[int, int], list[tuple[int, int]]] = {
        (r, c): [] for r in range(rows) for c in range(cols)
    }
    for r in range(rows):
        for c in range(cols):
            d = int(flow_dir[r, c])
            if d < 0:
                continue
            dr, dc = D8_OFFSETS[d]
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                upstream[(nr, nc)].append((r, c))
    return upstream


def delineate_watershed(
    outlet_row: int,
    outlet_col: int,
    flow_dir: np.ndarray,
) -> np.ndarray:
    """
    BFS upstream from (outlet_row, outlet_col) using the inverse flow map.

    Returns a bool array where True = cell drains to the outlet.
    """
    rows, cols = flow_dir.shape
    upstream_map = _build_upstream_map(flow_dir)
    mask = np.zeros((rows, cols), dtype=bool)
    mask[outlet_row, outlet_col] = True

    queue: deque[tuple[int, int]] = deque([(outlet_row, outlet_col)])
    while queue:
        r, c = queue.popleft()
        for pr, pc in upstream_map[(r, c)]:
            if not mask[pr, pc]:
                mask[pr, pc] = True
                queue.append((pr, pc))
    return mask


def _mask_to_polygon(
    mask: np.ndarray,
    dem_result: DEMResult,
) -> Polygon | MultiPolygon:
    """
    Convert a raster watershed mask to a simplified Shapely polygon.

    Uses unary_union of per-cell bounding boxes in UTM, then reprojects
    to WGS84 lon/lat for the GeoJSON output.
    """
    res = dem_result.resolution_m
    rows = dem_result.rows

    boxes = []
    for r, c in zip(*np.where(mask)):
        x_min_cell = dem_result.x_min + c * res
        # Row 0 = north; y increases southward in array, northward in UTM
        y_min_cell = dem_result.y_min + (rows - 1 - r) * res
        boxes.append(box(x_min_cell, y_min_cell, x_min_cell + res, y_min_cell + res))

    if not boxes:
        raise ValueError("Watershed mask is empty — no cells to form a polygon")

    union = unary_union(boxes)
    # Simplify to ~half a cell width to reduce vertex count
    union = union.simplify(res * 0.5, preserve_topology=True)

    # Reproject from UTM to WGS84
    t = Transformer.from_crs(
        f"EPSG:{dem_result.epsg}", "EPSG:4326", always_xy=True
    )

    def transform_coords(coords):
        return [t.transform(x, y) for x, y in coords]

    if isinstance(union, Polygon):
        exterior = transform_coords(union.exterior.coords)
        interiors = [transform_coords(ring.coords) for ring in union.interiors]
        return Polygon(exterior, interiors)
    else:
        polys = []
        for geom in union.geoms:
            exterior = transform_coords(geom.exterior.coords)
            interiors = [transform_coords(ring.coords) for ring in geom.interiors]
            polys.append(Polygon(exterior, interiors))
        return MultiPolygon(polys)


def select_pond_and_delineate(
    dem_result: DEMResult,
    terrain: TerrainResult,
    min_catchment_area_m2: float = 500.0,
    border_cells: int = 2,
    w_acc: float = 0.7,
    w_dep: float = 0.3,
) -> CatchmentResult:
    """
    Select the best pond outlet and delineate its watershed.

    Parameters
    ----------
    dem_result:             DEMResult from the DEM builder
    terrain:                TerrainResult from terrain analysis
    min_catchment_area_m2:  minimum viable catchment area in m²
    border_cells:           cells near the boundary to exclude from selection
    w_acc / w_dep:          scoring weights (must sum to 1.0)

    Returns
    -------
    CatchmentResult with pond site info and catchment statistics.

    Raises
    ------
    ValueError if no valid pond site can be found.
    """
    rows, cols = terrain.flow_acc.shape
    res = dem_result.resolution_m
    cell_area_m2 = res ** 2
    min_flow_acc = max(1.0, min_catchment_area_m2 / cell_area_m2)

    # ---- Build score grid ----
    facc = terrain.flow_acc.astype(np.float64)
    depression_depth = np.maximum(0.0, terrain.filled.astype(np.float64) - dem_result.elevation.astype(np.float64))

    def _norm(arr: np.ndarray) -> np.ndarray:
        lo, hi = arr.min(), arr.max()
        return (arr - lo) / (hi - lo + 1e-9)

    score = w_acc * _norm(facc) + w_dep * _norm(depression_depth)

    # Mask: must be interior, must meet min flow accumulation, flow dir valid
    interior = np.zeros((rows, cols), dtype=bool)
    interior[border_cells: rows - border_cells, border_cells: cols - border_cells] = True

    valid = interior & (facc >= min_flow_acc) & (terrain.flow_dir >= 0)

    if not valid.any():
        raise ValueError(
            f"No valid pond site found — no cell meets min_catchment_area_m2="
            f"{min_catchment_area_m2} m² with current resolution {res} m. "
            "Try increasing resolution_m or lowering min_catchment_area_m2."
        )

    score[~valid] = -np.inf
    flat_idx = int(np.argmax(score))
    out_r, out_c = np.unravel_index(flat_idx, score.shape)

    # ---- Delineate watershed ----
    mask = delineate_watershed(int(out_r), int(out_c), terrain.flow_dir)
    watershed_cells = int(mask.sum())
    area_m2 = watershed_cells * cell_area_m2
    area_ha = area_m2 / 10_000.0

    if area_m2 < min_catchment_area_m2:
        raise ValueError(
            f"Best pond site catchment ({area_m2:.0f} m²) is below "
            f"min_catchment_area_m2={min_catchment_area_m2}. "
            "Try lowering min_catchment_area_m2 or using a finer resolution."
        )

    # ---- Pond site coordinates ----
    easting, northing = dem_result.cell_to_utm(int(out_r), int(out_c))
    lon, lat = dem_result.utm_to_lonlat(easting, northing)
    elevation_m = float(dem_result.elevation[out_r, out_c])
    flow_acc_cells = int(terrain.flow_acc[out_r, out_c])

    pond_site = PondSite(
        row=int(out_r),
        col=int(out_c),
        lat=round(lat, 6),
        lon=round(lon, 6),
        elevation_m=round(elevation_m, 2),
        flow_accumulation_cells=flow_acc_cells,
    )

    # ---- Slope statistics over watershed ----
    ws_slope = terrain.slope[mask]
    mean_slope = float(ws_slope.mean()) if mask.any() else 0.0
    max_slope  = float(ws_slope.max())  if mask.any() else 0.0

    # ---- Elevation statistics over watershed ----
    ws_elev = dem_result.elevation[mask]
    min_elev = float(ws_elev.min()) if mask.any() else elevation_m
    max_elev = float(ws_elev.max()) if mask.any() else elevation_m
    relief   = round(max_elev - min_elev, 2)

    # ---- Build catchment polygon ----
    polygon = _mask_to_polygon(mask, dem_result)
    geojson = mapping(polygon)

    # ---- Water volume and pond sizing (rational method) ----
    # Central India representative annual rainfall ~800mm
    annual_rainfall_mm = 800.0
    if mean_slope < 5.0:
        runoff_coeff = 0.35
    elif mean_slope < 10.0:
        runoff_coeff = 0.45
    else:
        runoff_coeff = 0.55
    rainfall_m = annual_rainfall_mm / 1000.0
    water_volume_m3 = round(rainfall_m * area_m2 * runoff_coeff, 2)
    water_volume_liters = round(water_volume_m3 * 1000.0, 2)
    pond_depth = max(0.5, min(round(relief * 0.5, 2), 3.0))
    pond_surface_area = round(water_volume_m3 / pond_depth, 2)
    storage_capacity_m3 = round(pond_surface_area * pond_depth, 2)

    return CatchmentResult(
        pond_site=pond_site,
        mask=mask,
        area_m2=round(area_m2, 2),
        area_hectares=round(area_ha, 4),
        mean_slope_pct=round(mean_slope, 2),
        max_slope_pct=round(max_slope, 2),
        min_elevation_m=round(min_elev, 2),
        max_elevation_m=round(max_elev, 2),
        relief_m=relief,
        watershed_cell_count=watershed_cells,
        annual_rainfall_mm=annual_rainfall_mm,
        runoff_coefficient=runoff_coeff,
        expected_water_volume_m3=water_volume_m3,
        expected_water_volume_liters=water_volume_liters,
        recommended_pond_depth_m=pond_depth,
        recommended_pond_surface_area_m2=pond_surface_area,
        recommended_storage_capacity_m3=storage_capacity_m3,
        boundary_geojson=dict(geojson),
    )
