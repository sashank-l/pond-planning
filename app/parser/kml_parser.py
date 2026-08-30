"""KML/KMZ contour map parser.

Handles:
- KMZ (zip) unwrapping
- Namespace-agnostic XPath so it tolerates custom attributes like py:pytype
- Returns a generic ContourDataset (list of elevation→polyline pairs)
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

from lxml import etree


@dataclass
class ContourLine:
    elevation: float
    points: list[tuple[float, float]]  # (lon, lat)


@dataclass
class ContourDataset:
    contours: list[ContourLine] = field(default_factory=list)

    @property
    def elevation_min(self) -> float:
        return min(c.elevation for c in self.contours)

    @property
    def elevation_max(self) -> float:
        return max(c.elevation for c in self.contours)

    @property
    def contour_interval(self) -> float:
        """Best-guess contour interval from the sorted unique elevations."""
        elevs = sorted({round(c.elevation, 6) for c in self.contours})
        if len(elevs) < 2:
            return 0.0
        diffs = [elevs[i + 1] - elevs[i] for i in range(len(elevs) - 1)]
        # Mode of rounded diffs
        rounded = [round(d, 3) for d in diffs if d > 0]
        if not rounded:
            return 0.0
        return float(max(set(rounded), key=rounded.count))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_COORDS_RE = re.compile(r"[^\d.\-,\s]+")  # strip garbage chars


def _strip_ns(tag: str) -> str:
    """Return local name without namespace, e.g. '{kml}Placemark' → 'Placemark'."""
    return tag.split("}")[-1] if "}" in tag else tag


def _parse_coordinates(text: str) -> list[tuple[float, float]]:
    """Parse KML <coordinates> text into list of (lon, lat) tuples."""
    points: list[tuple[float, float]] = []
    text = _COORDS_RE.sub(" ", text).strip()
    for token in text.split():
        parts = token.split(",")
        if len(parts) >= 2:
            try:
                lon, lat = float(parts[0]), float(parts[1])
                points.append((lon, lat))
            except ValueError:
                pass
    return points


def _extract_elevation(placemark: etree._Element) -> float | None:
    """
    Try multiple strategies to pull elevation out of a Placemark:
    1. <name> is a bare number
    2. <description> contains a number
    3. altitude value in any <coordinates> triplet (lon,lat,alt)
    Returns None if no elevation found.
    """
    # Strategy 1: <name> tag
    for child in placemark:
        if _strip_ns(child.tag) == "name" and child.text:
            try:
                return float(child.text.strip())
            except ValueError:
                pass

    # Strategy 2: <description>
    for child in placemark:
        if _strip_ns(child.tag) == "description" and child.text:
            nums = re.findall(r"[-+]?\d+(?:\.\d+)?", child.text)
            if nums:
                try:
                    return float(nums[0])
                except ValueError:
                    pass

    # Strategy 3: altitude in coordinates
    for el in placemark.iter():
        if _strip_ns(el.tag) == "coordinates" and el.text:
            for token in el.text.strip().split():
                parts = token.split(",")
                if len(parts) >= 3:
                    try:
                        alt = float(parts[2])
                        if alt != 0.0:
                            return alt
                    except ValueError:
                        pass
    return None


def _parse_tree(tree: etree._Element) -> ContourDataset:
    """Walk the element tree and extract all contour lines."""
    dataset = ContourDataset()

    for placemark in tree.iter():
        if _strip_ns(placemark.tag) != "Placemark":
            continue

        elevation = _extract_elevation(placemark)
        if elevation is None:
            continue

        # Find coordinates in LineString elements only — skip LinearRing
        # (LinearRing is used for Polygon boundaries, e.g. bounding-box placemarks)
        for el in placemark.iter():
            local = _strip_ns(el.tag)
            if local != "coordinates" or not el.text:
                continue
            parent = el.getparent()
            if parent is not None and _strip_ns(parent.tag) == "LinearRing":
                continue  # skip polygon boundary rings
            pts = _parse_coordinates(el.text)
            if len(pts) >= 2:
                dataset.contours.append(ContourLine(elevation=elevation, points=pts))

    return dataset


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_kml_bytes(data: bytes) -> ContourDataset:
    """Parse raw KML bytes and return a ContourDataset."""
    tree = etree.fromstring(data)
    return _parse_tree(tree)


def parse_kmz_bytes(data: bytes) -> ContourDataset:
    """Unzip KMZ bytes, find the root KML document, parse and return ContourDataset."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        kml_names = [n for n in zf.namelist() if n.lower().endswith(".kml")]
        if not kml_names:
            raise ValueError("KMZ archive contains no .kml file")
        # Prefer doc.kml / root-level files; fall back to first match
        preferred = [n for n in kml_names if "/" not in n] or kml_names
        kml_bytes = zf.read(preferred[0])
    return parse_kml_bytes(kml_bytes)


def parse_file(path: str | Path) -> ContourDataset:
    """Parse a KML or KMZ file from disk."""
    p = Path(path)
    data = p.read_bytes()
    ext = p.suffix.lower()
    if ext == ".kmz":
        return parse_kmz_bytes(data)
    elif ext == ".kml":
        return parse_kml_bytes(data)
    else:
        raise ValueError(f"Unsupported file extension: {ext!r}. Expected .kml or .kmz")


def parse_upload(file_obj: IO[bytes], filename: str) -> ContourDataset:
    """Parse from an open file-like object (e.g. FastAPI UploadFile.file)."""
    ext = Path(filename).suffix.lower()
    data = file_obj.read()
    if ext == ".kmz":
        return parse_kmz_bytes(data)
    elif ext == ".kml":
        return parse_kml_bytes(data)
    else:
        raise ValueError(f"Unsupported file extension: {ext!r}. Expected .kml or .kmz")
