"""Terrain analysis: depression fill, D8 flow direction, flow accumulation.

All operations are pure numpy — no GDAL/richdem/pysheds required.

Algorithms
----------
Depression fill : Priority-flood (Wang & Liu 2006 variant).
                  Uses a min-heap; fills cells to their spill elevation.
D8 flow direction: Standard 8-direction drainage; each cell drains to its
                   lowest-elevation neighbour. Encodes direction as integer
                   0-7 (N, NE, E, SE, S, SW, W, NW) or -1 for outlets.
Flow accumulation: Single-pass topological sort (Tarjan-style via in-degree
                   counting); no recursion to avoid stack overflows on large
                   grids.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass

import numpy as np

# D8 direction offsets (row_delta, col_delta) for directions 0–7
# 0=N, 1=NE, 2=E, 3=SE, 4=S, 5=SW, 6=W, 7=NW
D8_OFFSETS = [
    (-1,  0),  # N
    (-1,  1),  # NE
    ( 0,  1),  # E
    ( 1,  1),  # SE
    ( 1,  0),  # S
    ( 1, -1),  # SW
    ( 0, -1),  # W
    (-1, -1),  # NW
]

# Weight by distance (diagonal cells are sqrt(2) further)
D8_WEIGHTS = [1.0, 1.414, 1.0, 1.414, 1.0, 1.414, 1.0, 1.414]


@dataclass
class TerrainResult:
    filled: np.ndarray       # float32 depression-filled DEM
    flow_dir: np.ndarray     # int8  D8 direction (0-7), -1 at boundary outlets
    flow_acc: np.ndarray     # float32 flow accumulation (cells drained through)
    slope: np.ndarray        # float32 mean slope in percent (for stats)


def fill_depressions(dem: np.ndarray) -> np.ndarray:
    """
    Priority-flood depression filling (Wang & Liu 2006).

    Returns a copy of `dem` where interior depressions are raised to their
    spill point so that all water can drain to the boundary.
    """
    rows, cols = dem.shape
    filled = dem.astype(np.float64).copy()

    # Initialise: add all boundary cells to the priority queue
    processed = np.zeros((rows, cols), dtype=bool)
    heap: list[tuple[float, int, int]] = []

    for r in range(rows):
        for c in [0, cols - 1]:
            if not processed[r, c]:
                heapq.heappush(heap, (filled[r, c], r, c))
                processed[r, c] = True
    for c in range(cols):
        for r in [0, rows - 1]:
            if not processed[r, c]:
                heapq.heappush(heap, (filled[r, c], r, c))
                processed[r, c] = True

    while heap:
        elev, r, c = heapq.heappop(heap)
        for dr, dc in D8_OFFSETS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and not processed[nr, nc]:
                filled[nr, nc] = max(filled[nr, nc], elev)
                processed[nr, nc] = True
                heapq.heappush(heap, (filled[nr, nc], nr, nc))

    return filled.astype(np.float32)


def compute_flow_direction(filled: np.ndarray) -> np.ndarray:
    """
    Compute D8 flow direction for each cell.

    Each cell drains toward its lowest (steepest descent) neighbour.
    Boundary cells and flat cells with no lower neighbour are coded -1.

    Returns int8 array (0-7 = direction index from D8_OFFSETS, -1 = outlet/flat).
    """
    rows, cols = filled.shape
    fdir = np.full((rows, cols), -1, dtype=np.int8)
    f64 = filled.astype(np.float64)

    # Vectorised approach: for each of 8 directions compute the drop
    # then take the direction with maximum drop.
    max_drop = np.full((rows, cols), -np.inf)

    for d, (dr, dc) in enumerate(D8_OFFSETS):
        # Shift the DEM by the offset
        # Neighbour of (r, c) in direction d is at (r+dr, c+dc).
        # We want: nbr[r, c] = f64[r+dr, c+dc]
        # Valid for r in [max(0,-dr), rows-1-max(0,dr)], same for cols.
        nbr = np.full_like(f64, np.inf)
        r_dst = slice(max(0, -dr), rows - max(0,  dr))
        c_dst = slice(max(0, -dc), cols - max(0,  dc))
        r_src = slice(max(0,  dr), rows - max(0, -dr))
        c_src = slice(max(0,  dc), cols - max(0, -dc))
        nbr[r_dst, c_dst] = f64[r_src, c_src]

        drop = (f64 - nbr) / D8_WEIGHTS[d]
        better = drop > max_drop
        max_drop = np.where(better, drop, max_drop)
        fdir = np.where(better.astype(bool), np.int8(d), fdir).astype(np.int8)

    # Cells where max_drop <= 0 (flat / sink) → -1
    fdir[max_drop <= 0] = -1

    # Force boundary cells to -1 (they drain off the edge)
    fdir[0, :] = -1
    fdir[-1, :] = -1
    fdir[:, 0] = -1
    fdir[:, -1] = -1

    return fdir


def compute_flow_accumulation(fdir: np.ndarray) -> np.ndarray:
    """
    Compute flow accumulation via topological sort.

    Each cell starts with accumulation = 1 (itself).  Accumulation is
    propagated from upstream to downstream in topological order determined
    by in-degree counting (Kahn's algorithm).

    Returns float32 array of accumulated cell counts.
    """
    rows, cols = fdir.shape
    acc = np.ones((rows, cols), dtype=np.float64)

    # Build in-degree count (how many cells flow into each cell)
    in_degree = np.zeros((rows, cols), dtype=np.int32)
    for r in range(rows):
        for c in range(cols):
            d = int(fdir[r, c])
            if d < 0:
                continue
            dr, dc = D8_OFFSETS[d]
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                in_degree[nr, nc] += 1

    # Queue cells with no upstream (in_degree == 0)
    from collections import deque
    queue: deque[tuple[int, int]] = deque()
    for r in range(rows):
        for c in range(cols):
            if in_degree[r, c] == 0:
                queue.append((r, c))

    while queue:
        r, c = queue.popleft()
        d = int(fdir[r, c])
        if d < 0:
            continue
        dr, dc = D8_OFFSETS[d]
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            acc[nr, nc] += acc[r, c]
            in_degree[nr, nc] -= 1
            if in_degree[nr, nc] == 0:
                queue.append((nr, nc))

    return acc.astype(np.float32)


def compute_slope(dem: np.ndarray, resolution_m: float) -> np.ndarray:
    """
    Compute slope in percent using central-difference finite difference.

    Returns float32 array, same shape as `dem`.
    """
    dy, dx = np.gradient(dem.astype(np.float64), resolution_m)
    slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
    slope_pct = np.tan(slope_rad) * 100.0
    return slope_pct.astype(np.float32)


def analyze_terrain(dem: np.ndarray, resolution_m: float) -> TerrainResult:
    """
    Full terrain analysis pipeline.

    Parameters
    ----------
    dem:          float32 2-D elevation array (row 0 = north)
    resolution_m: grid cell size in metres

    Returns
    -------
    TerrainResult with filled DEM, flow direction, flow accumulation, slope.
    """
    filled = fill_depressions(dem)
    fdir = compute_flow_direction(filled)
    facc = compute_flow_accumulation(fdir)
    slope = compute_slope(filled, resolution_m)
    return TerrainResult(filled=filled, flow_dir=fdir, flow_acc=facc, slope=slope)
