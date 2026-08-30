# Contour-Based Pond Catchment Analysis API

A FastAPI backend that accepts a contour map (KML/KMZ), analyzes terrain, identifies a suitable pond location, and returns the corresponding catchment area as structured JSON.

## Architecture

```
Upload (KML/KMZ)
      |
      v
[1] Parser layer        -> ContourDataset (elevation, polylines in lon/lat)
      |
      v
[2] Projection layer     -> reproject lon/lat to local UTM meters (pyproj)
      |
      v
[3] DEM builder layer    -> rasterize contours + scipy.interpolate.griddata
      |
      v
[4] Terrain analysis     -> depression fill, D8 flow direction, flow accumulation
      |
      v
[5] Pond site selector   -> heuristic scoring over candidate cells
      |
      v
[6] Catchment delineator -> watershed trace from chosen outlet -> boundary polygon
      |
      v
[7] Response builder     -> JSON (pond site, catchment polygon, area, stats)
```

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open `http://localhost:8000/docs` for the interactive Swagger UI.

## API

### `POST /analyzeContour`

| Field | Type | Default | Description |
|---|---|---|---|
| `file` | file | required | `.kml` or `.kmz` contour map |
| `resolution_m` | float | 10.0 | Grid resolution in metres |
| `min_catchment_area_m2` | float | 500.0 | Minimum acceptable catchment area |

### `GET /health`

Returns `{"status": "ok"}`.

## Deployment

See `deploy/` for systemd unit file, deploy script, and optional Nginx config.

## Testing

```bash
pytest tests/ -v
```
