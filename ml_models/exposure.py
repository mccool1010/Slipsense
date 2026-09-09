"""
exposure.py
Turn runout corridors into consequence: what buildings and roads lie in their path.

A hazard map says where debris goes. It does not say whether that matters. Intersecting
the modelled transit and deposition zones with OpenStreetMap buildings and roads
converts a susceptibility surface into a statement a disaster-management office can act
on - "this corridor crosses 14 buildings and 380 m of road" - and it lets corridors be
ranked by what they threaten rather than by raw model score.

Buildings and roads come from the Overpass API (no key required). Queries are issued per
sub-box over the corridor extent only, because a single request covering the whole
110 km tile would time out.

Outputs:
  backend/rasters/v2/exposure_summary.json      totals and the worst corridors
  backend/rasters/v2/runout_paths_exposed.geojson  corridors with exposure attributes

Run:  python ml_models/exposure.py [--box 0.1] [--max-boxes 40]
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
PATHS = V2 / "runout_paths.geojson"
SUMMARY = V2 / "exposure_summary.json"
OUT_PATHS = V2 / "runout_paths_exposed.geojson"
CACHE = ROOT / "data" / "osm_cache.json"

OVERPASS = "https://overpass-api.de/api/interpreter"


def log(msg, t0=None):
    print(f"{msg}{f'  [{time.time() - t0:6.1f}s]' if t0 else ''}", flush=True)


def query_overpass(south, west, north, east, session, cache):
    """Fetch building footprints and road centrelines for one bounding box."""
    key = f"{south:.3f},{west:.3f},{north:.3f},{east:.3f}"
    if key in cache:
        return cache[key]

    q = (f"[out:json][timeout:90];("
         f'way["building"]({south},{west},{north},{east});'
         f'way["highway"]({south},{west},{north},{east});'
         f");out geom;")
    for attempt in range(4):
        try:
            r = session.post(OVERPASS, data={"data": q}, timeout=120)
            if r.status_code in (429, 504):
                time.sleep(15 * (attempt + 1))
                continue
            r.raise_for_status()
            elements = r.json().get("elements", [])
            out = []
            for el in elements:
                geom = el.get("geometry")
                if not geom:
                    continue
                tags = el.get("tags", {})
                kind = "building" if "building" in tags else "road"
                out.append({"kind": kind,
                            "coords": [[p["lon"], p["lat"]] for p in geom]})
            cache[key] = out
            return out
        except requests.RequestException:
            time.sleep(10 * (attempt + 1))
    return []


def burn(features, kind, shape, transform, to_utm):
    """Rasterise OSM features of one kind onto the analysis grid."""
    mask = np.zeros(shape, dtype=bool)
    inv = ~transform
    h, w = shape
    for f in features:
        if f["kind"] != kind:
            continue
        lon = np.array([c[0] for c in f["coords"]], dtype=float)
        lat = np.array([c[1] for c in f["coords"]], dtype=float)
        x, y = to_utm.transform(lon, lat)
        cols, rows = inv * (x, y)
        cols = np.asarray(cols); rows = np.asarray(rows)
        for i in range(len(cols) - 1):
            steps = int(max(abs(cols[i + 1] - cols[i]),
                            abs(rows[i + 1] - rows[i]))) + 1
            cc = np.linspace(cols[i], cols[i + 1], steps).astype(int)
            rr = np.linspace(rows[i], rows[i + 1], steps).astype(int)
            ok = (rr >= 0) & (rr < h) & (cc >= 0) & (cc < w)
            mask[rr[ok], cc[ok]] = True
    return mask


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--box", type=float, default=0.1, help="query box size in degrees")
    ap.add_argument("--max-boxes", type=int, default=40)
    args = ap.parse_args()

    t0 = time.time()
    if not PATHS.exists():
        raise SystemExit(f"Missing {PATHS}. Run generate_runout_v2.py first.")

    with rasterio.open(V2 / "hazard_fused.tif") as src:
        zones = src.read(1)
        transform, shape, crs = src.transform, (src.height, src.width), src.crs
    transit = (zones == 2) | (zones == 1)      # transit or deposition
    res = abs(transform.a)

    to_wgs = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    to_utm = Transformer.from_crs("EPSG:4326", crs, always_xy=True)

    # Only query where debris actually goes.
    rows, cols = np.nonzero(transit)
    xs, ys = transform * (cols + 0.5, rows + 0.5)
    lon, lat = to_wgs.transform(np.asarray(xs), np.asarray(ys))

    step = args.box
    keys = {(np.floor(la / step) * step, np.floor(lo / step) * step)
            for la, lo in zip(lat, lon)}
    boxes = sorted(keys)[:args.max_boxes]
    log(f"Corridor extent spans {len(keys)} boxes of {step} deg; querying {len(boxes)}")

    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    session = requests.Session()
    session.headers.update({"User-Agent": "SlipSense/1.0 (landslide research)"})

    features = []
    for i, (blat, blon) in enumerate(boxes, 1):
        got = query_overpass(blat, blon, blat + step, blon + step, session, cache)
        features.extend(got)
        log(f"  box {i}/{len(boxes)} ({blat:.2f},{blon:.2f}): {len(got)} features")
        CACHE.write_text(json.dumps(cache))

    n_build = sum(1 for f in features if f["kind"] == "building")
    n_road = sum(1 for f in features if f["kind"] == "road")
    log(f"\nOSM: {n_build:,} buildings, {n_road:,} road segments", t0)
    if not features:
        raise SystemExit("No OSM features returned; nothing to intersect.")

    log("Rasterising and intersecting ...")
    build_mask = burn(features, "building", shape, transform, to_utm)
    road_mask = burn(features, "road", shape, transform, to_utm)

    # Count buildings, not cells: label connected footprints and test each once.
    labelled, n_labels = ndimage.label(build_mask)
    hit_labels = set(np.unique(labelled[transit & build_mask])) - {0}
    buildings_hit = len(hit_labels)
    road_cells_hit = int((road_mask & transit).sum())
    road_km_hit = road_cells_hit * res / 1000.0

    log(f"  buildings in corridors : {buildings_hit:,} of {n_labels:,} mapped")
    log(f"  road length in corridors: {road_km_hit:.2f} km")

    # Per-corridor exposure, so paths can be ranked by what they threaten.
    paths = json.loads(PATHS.read_text())
    inv = ~transform
    h, w = shape
    ranked = []
    for idx, f in enumerate(paths["features"]):
        xy = np.asarray(f["geometry"]["coordinates"], dtype=float)
        # The corridor file is WGS84 (GeoJSON requires it); the rasters are projected,
        # so the centrelines must be converted before they can index into a grid.
        px, py = to_utm.transform(xy[:, 0], xy[:, 1])
        cols_p, rows_p = inv * (np.asarray(px), np.asarray(py))
        rr = np.asarray(rows_p).astype(int)
        cc = np.asarray(cols_p).astype(int)
        ok = (rr >= 0) & (rr < h) & (cc >= 0) & (cc < w)
        rr, cc = rr[ok], cc[ok]
        if len(rr) == 0:
            continue
        # Widen to the corridor, not just the centreline: debris is not one cell wide.
        near = np.zeros(shape, dtype=bool)
        near[rr, cc] = True
        near = ndimage.binary_dilation(near, np.ones((5, 5), bool)) & transit

        labs = set(np.unique(labelled[near & build_mask])) - {0}
        roads = int((road_mask & near).sum()) * res / 1000.0
        f["properties"]["buildings_at_risk"] = len(labs)
        f["properties"]["road_km_at_risk"] = round(roads, 3)
        ranked.append((len(labs), roads, idx, f["properties"]))

    ranked.sort(key=lambda r: (-r[0], -r[1]))
    OUT_PATHS.write_text(json.dumps(paths))

    top = [{"path_index": idx, "buildings_at_risk": b,
            "road_km_at_risk": round(r, 3),
            "length_m": props.get("length_m"),
            "max_velocity_ms": props.get("max_velocity_ms")}
           for b, r, idx, props in ranked[:15]]

    # Exposure per connected debris corridor, which is what actually threatens things.
    # The traced centrelines are a few hundred short representative lines and mostly
    # miss the built-up ground, so ranking them alone reports zeros even where the
    # zones as a whole intersect tens of kilometres of road.
    corridor_labels, n_corridors = ndimage.label(
        transit, structure=np.ones((3, 3), dtype=int))
    log(f"Ranking {n_corridors:,} connected corridors by exposure ...")

    road_in = road_mask & transit
    build_in = build_mask & transit
    zones_exposed = []
    if n_corridors:
        road_counts = ndimage.sum(road_in, corridor_labels,
                                  index=np.arange(1, n_corridors + 1))
        sizes = ndimage.sum(transit, corridor_labels,
                            index=np.arange(1, n_corridors + 1))
        # Buildings per corridor: map each hit footprint to the corridor it sits in.
        hit_cells = np.nonzero(build_in)
        per_corridor_buildings = {}
        for r_, c_ in zip(*hit_cells):
            lab = int(corridor_labels[r_, c_])
            if lab:
                per_corridor_buildings.setdefault(lab, set()).add(
                    int(labelled[r_, c_]))

        for lab in range(1, n_corridors + 1):
            b = len(per_corridor_buildings.get(lab, ()))
            rkm = float(road_counts[lab - 1]) * res / 1000.0
            if b == 0 and rkm <= 0:
                continue
            zones_exposed.append({
                "corridor_id": lab,
                "buildings_at_risk": b,
                "road_km_at_risk": round(rkm, 3),
                "area_ha": round(float(sizes[lab - 1]) * res * res / 1e4, 2),
            })
    zones_exposed.sort(key=lambda d: (-d["buildings_at_risk"], -d["road_km_at_risk"]))

    SUMMARY.write_text(json.dumps({
        "osm_buildings_mapped": n_labels,
        "osm_road_segments": n_road,
        "buildings_in_corridors": buildings_hit,
        "road_km_in_corridors": round(road_km_hit, 3),
        "boxes_queried": len(boxes),
        "boxes_total": len(keys),
        "corridors": len(paths["features"]),
        "top_centrelines": top,
        "exposed_corridors": zones_exposed[:25],
        "n_exposed_corridors": len(zones_exposed),
    }, indent=2))

    log(f"\nWrote {SUMMARY.relative_to(ROOT)} and {OUT_PATHS.name}")
    log(f"\n{len(zones_exposed)} corridors intersect something built:")
    for z in zones_exposed[:8]:
        log(f"  corridor {z['corridor_id']:6d}: {z['buildings_at_risk']:3d} buildings, "
            f"{z['road_km_at_risk']:6.2f} km road, {z['area_ha']:8.1f} ha")
    log("Done.", t0)


if __name__ == "__main__":
    main()
