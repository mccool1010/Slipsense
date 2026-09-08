"""
geo_io.py
Minimal ESRI Shapefile reader (points and polygons) built on struct + shapely.

The project venv has no geopandas/fiona, and the only shapefiles we need to read
are simple point inventories and single-polygon boundaries. Parsing them directly
avoids adding a heavy geospatial stack just for two file types.

Shapefile spec: ESRI Shapefile Technical Description (July 1998).
"""

import struct
from pathlib import Path

import numpy as np

SHP_NULL = 0
SHP_POINT = 1
SHP_POLYLINE = 3
SHP_POLYGON = 5


def _records(shp_path):
    """Yield (shape_type, payload_bytes) for every record in a .shp file."""
    with open(shp_path, "rb") as f:
        f.seek(100)  # skip the 100-byte file header
        while True:
            header = f.read(8)
            if len(header) < 8:
                return
            _rec_num, content_len = struct.unpack(">II", header)
            payload = f.read(content_len * 2)
            if len(payload) < 4:
                return
            shape_type = struct.unpack("<I", payload[:4])[0]
            yield shape_type, payload


def read_points(shp_path):
    """Read a point shapefile into an (N, 2) array of x, y in the file's own CRS."""
    pts = []
    for shape_type, payload in _records(shp_path):
        if shape_type == SHP_POINT:
            pts.append(struct.unpack("<dd", payload[4:20]))
    if not pts:
        raise ValueError(f"No point records found in {shp_path}")
    return np.asarray(pts, dtype=float)


def read_parts(shp_path, want_type):
    """Read a multi-part shapefile (polygon or polyline) as a list of coordinate arrays."""
    polys = []
    for shape_type, payload in _records(shp_path):
        if shape_type != want_type:
            continue
        num_parts, num_points = struct.unpack("<II", payload[36:44])
        parts_end = 44 + num_parts * 4
        parts = struct.unpack(f"<{num_parts}I", payload[44:parts_end])
        coords = np.frombuffer(
            payload[parts_end:parts_end + num_points * 16], dtype="<f8"
        ).reshape(num_points, 2)
        bounds = list(parts) + [num_points]
        for i in range(num_parts):
            polys.append(coords[bounds[i]:bounds[i + 1]].copy())
    return polys


def read_polygons(shp_path):
    """Read a polygon shapefile as a list of rings, each an (M, 2) coordinate array."""
    return read_parts(shp_path, SHP_POLYGON)


def read_polylines(shp_path):
    """Read a polyline shapefile (e.g. a river network) as a list of (M, 2) arrays."""
    return read_parts(shp_path, SHP_POLYLINE)


def read_prj(shp_path):
    """Return the WKT of the sidecar .prj file, or None when absent."""
    prj = Path(shp_path).with_suffix(".prj")
    if not prj.exists():
        return None
    return prj.read_text(encoding="latin1").strip()


def record_count(shp_path):
    """Count records cheaply via the .shx index: (filesize - 100 header) / 8 per record."""
    shx = Path(shp_path).with_suffix(".shx")
    return (shx.stat().st_size - 100) // 8
