"""Parser unit tests.

Runs against the real sample file contours_1m.kml to assert:
- Correct number of contour lines
- Plausible elevation range
- No exceptions raised
- contour_interval detection
"""

import os
import pytest
from pathlib import Path

SAMPLE_KML = Path(__file__).parent.parent / "contours_1m.kml"

# Skip if sample file not present (CI without large files)
pytestmark = pytest.mark.skipif(
    not SAMPLE_KML.exists(), reason="contours_1m.kml not present"
)


def test_parse_sample_kml_no_exception():
    from app.parser.kml_parser import parse_file
    ds = parse_file(SAMPLE_KML)
    assert len(ds.contours) > 0, "Expected at least one contour line"


def test_parse_sample_kml_elevation_range():
    from app.parser.kml_parser import parse_file
    ds = parse_file(SAMPLE_KML)
    assert ds.elevation_min >= 250.0, f"Elevation min {ds.elevation_min} unexpectedly low"
    assert ds.elevation_max <= 320.0, f"Elevation max {ds.elevation_max} unexpectedly high"
    assert ds.elevation_min < ds.elevation_max


def test_parse_sample_kml_contour_count():
    from app.parser.kml_parser import parse_file
    ds = parse_file(SAMPLE_KML)
    # Sample file has ~2711 contour polylines
    assert len(ds.contours) >= 100, f"Too few contours: {len(ds.contours)}"


def test_parse_sample_kml_contour_interval():
    from app.parser.kml_parser import parse_file
    ds = parse_file(SAMPLE_KML)
    interval = ds.contour_interval
    assert interval > 0.0, "Contour interval should be positive"
    # For the sample file, expect roughly 1m
    assert 0.5 <= interval <= 5.0, f"Unexpected contour interval: {interval}"


def test_parse_kml_bytes_minimal():
    """Test that a minimal hand-crafted KML round-trips correctly."""
    from app.parser.kml_parser import parse_kml_bytes
    kml = b"""<?xml version="1.0"?>
    <kml xmlns="http://www.opengis.net/kml/2.2">
      <Document>
        <Placemark>
          <name>270</name>
          <LineString>
            <coordinates>81.29,21.25,0 81.30,21.26,0 81.31,21.27,0</coordinates>
          </LineString>
        </Placemark>
        <Placemark>
          <name>271</name>
          <LineString>
            <coordinates>81.31,21.27,0 81.32,21.28,0 81.33,21.29,0</coordinates>
          </LineString>
        </Placemark>
      </Document>
    </kml>"""
    ds = parse_kml_bytes(kml)
    assert len(ds.contours) == 2
    elevations = {c.elevation for c in ds.contours}
    assert 270.0 in elevations
    assert 271.0 in elevations


def test_parse_unsupported_format_raises():
    from app.parser.kml_parser import parse_file
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
        f.write(b"garbage")
        tmp = f.name
    with pytest.raises(ValueError, match="Unsupported"):
        parse_file(tmp)
    os.unlink(tmp)
