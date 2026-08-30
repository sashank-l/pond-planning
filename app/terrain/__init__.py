"""Terrain package."""
from .analysis import TerrainResult, analyze_terrain, fill_depressions, compute_flow_direction, compute_flow_accumulation, compute_slope

__all__ = [
    "TerrainResult",
    "analyze_terrain",
    "fill_depressions",
    "compute_flow_direction",
    "compute_flow_accumulation",
    "compute_slope",
]
