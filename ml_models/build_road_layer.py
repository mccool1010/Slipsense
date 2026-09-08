"""
build_road_layer.py
Distance-to-road surface for the training tile.

Road proximity earns its place twice over.

As a **predictor**, road cuts are among the strongest anthropogenic controls on shallow
failure in the Western Ghats: excavation removes toe support, and the cut face
concentrates drainage.

As a **diagnostic**, it is the sharpest test available for the inventory-bias
hypothesis. The baseline comparison showed the 12-feature model beating relative relief
on its own inventory but *not* on 106 independent events, which is what you would see if
the 279 training points were mapped preferentially along accessible ground. If distance
to road turns out to dominate the feature importances, that is direct evidence the model
is partly learning where landslides get *recorded* rather than where slopes fail.

Roads come from OpenStreetMap via Overpass, queried in coarse boxes across the tile.

Output: backend/rasters/v2/dist_road.tif

Run:  python ml_models/build_road_layer.py [--box 0.25]
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import rasterio
import requests
from pyproj import Transformer
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "backend" / "rasters" / "v2"
OUT = V2 / "dist_road.tif"
CACHE = ROOT / "data" / "osm_roads_cache.json"
OVERPASS = "https://overpass-api.de/api/interpreter"

# Motorable roads only. Footpaths and tracks are mapped far less consistently in rural
# Kerala, so including them would encode OSM coverage rather than real access.
ROAD_CLASSES = ("motorway|trunk|primary|secondary|tertiary|unclassified|residential"
                "|service|road")


def log(msg, t0=None):
    print(f"{msg}{f'  [{time.time() - t0:6.1f}s]' if t0 else ''}", flush=True)


def query_roads(south, west, north, east, session, cache):
    key = f"{south:.3f},{west:.3f},{north:.3f},{east:.3f}"
    if key in cache:
        return cache[key]
    q = (f'[out:json][timeout:120];'
         f'way["highway"~"^({ROAD_CLASSES})$"]({south},{west},{north},{east});'
         f'out geom;')
    for attempt in range(4):
        try:
            r = session.post(OVERPASS, data={"data": q}, timeout=180)
            if r.status_code in (429, 504):
                time.sleep(20 * (attempt + 1))
                continue
            r.raise_for_status()
            out = [[[p["lon"], p["lat"]] for p in el["geometry"]]
                   for el in r.json().get("elements", []) if el.get("geometry")]
            cache[key] = out
            return out
        except requests.RequestException:
            time.sleep(12 * (attempt + 1))
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--box", type=float, default=0.25)
    args = ap.parse_args()
    t0 = time.time()

    with rasterio.open(V2 / "elevation.tif") as src:
        profile = src.profile.copy()
        transform, shape, crs = src.transform, (src.height, src.width), src.crs
        nodata = ~np.isfinite(src.read(1))
    res = abs(transform.a)

    to_wgs = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    to_utm = Transformer.from_crs("EPSG:4326", crs, always_xy=True)

    h, w = shape
    corners_x, corners_y = zip(*[transform * (c, r)
                                 for r in (0, h) for c in (0, w)])
    lon, lat = to_wgs.transform(np.array(corners_x), np.array(corners_y))
    step = args.box
    lat0 = np.floor(lat.min() / step) * step
    lon0 = np.floor(lon.min() / step) * step
    boxes = [(la, lo)
             for la in np.arange(lat0, lat.max() + step, step)
             for lo in np.arange(lon0, lon.max() + step, step)]
    log(f"Tile spans {lat.min():.2f}-{lat.max():.2f}N, "
        f"{lon.min():.2f}-{lon.max():.2f}E -> {len(boxes)} boxes of {step} deg")

    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    session = requests.Session()
    session.headers.update({"User-Agent": "SlipSense/1.0 (landslide research)"})

    lines = []
    for i, (blat, blon) in enumerate(boxes, 1):
        got = query_roads(blat, blon, blat + step, blon + step, session, cache)
        lines.extend(got)
        log(f"  box {i}/{len(boxes)} ({blat:.2f},{blon:.2f}): {len(got)} ways")
        CACHE.write_text(json.dumps(cache))

    log(f"\n{len(lines):,} road ways total", t0)
    if not lines:
        raise SystemExit("No roads returned")

    log("Rasterising road network ...")
    mask = np.zeros(shape, dtype=bool)
    inv = ~transform
    for line in lines:
        arr = np.asarray(line, dtype=float)
        if len(arr) < 2:
            continue
        x, y = to_utm.transform(arr[:, 0], arr[:, 1])
        cols, rows = inv * (x, y)
        cols = np.asarray(cols); rows = np.asarray(rows)
        for i in range(len(cols) - 1):
            steps = int(max(abs(cols[i + 1] - cols[i]),
                            abs(rows[i + 1] - rows[i]))) + 1
            cc = np.linspace(cols[i], cols[i + 1], steps).astype(int)
            rr = np.linspace(rows[i], rows[i + 1], steps).astype(int)
            ok = (rr >= 0) & (rr < h) & (cc >= 0) & (cc < w)
            mask[rr[ok], cc[ok]] = True
    log(f"  {int(mask.sum()):,} road cells ({100 * mask.mean():.2f}% of grid)")

    dist = ndimage.distance_transform_edt(~mask, sampling=res).astype(np.float32)
    dist[nodata] = np.nan

    profile.update(dtype="float32", count=1, nodata=np.nan, compress="lzw")
    with rasterio.open(OUT, "w", **profile) as dst:
        dst.write(dist, 1)

    finite = dist[np.isfinite(dist)]
    log(f"\nWrote {OUT.relative_to(ROOT)}")
    log(f"  distance to road  median {np.median(finite):.0f} m  "
        f"p90 {np.percentile(finite, 90):.0f} m  max {finite.max():.0f} m")
    log("Done.", t0)


if __name__ == "__main__":
    main()
