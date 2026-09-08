"""
sentinel_inventory.py
Map landslide scars from Sentinel-2 change detection, to build an inventory that is
independent of the 279 points everything else here rests on.

This is the missing piece the rest of the analysis keeps pointing at. The current model
beats relative relief when predicting its own inventory but not when ranking independent
events (`baseline_report.md`), and the road-proximity probe ruled out the most obvious
explanation without settling the question (`augmented_report.md`). An inventory produced
by a different process - satellite observation rather than field mapping - is what
distinguishes "the model is overfitting how those points were collected" from "the
independent catalog is too imprecise to measure against".

It also unlocks two things asked for from the start: scar **polygons**, which make IoU
and Dice meaningful for a segmentation model, and **dated** events, which are the
prerequisite for a deployable rainfall intensity-duration threshold.

Method. Landslides strip vegetation, so a scar shows as a sharp NDVI drop between a
pre-event and a post-event image, on ground steep enough to fail. Optical imagery cannot
see through the monsoon that triggers these failures, so scenes are taken from the dry
windows either side of it: the pair brackets the monsoon rather than catching the event.

    NDVI = (NIR - Red) / (NIR + Red)
    scar candidate  =  NDVI drop > threshold
                       AND post-event NDVI low (bare, not merely thinner canopy)
                       AND slope >= minimum (excludes harvest, clearing, water)
                       AND patch area within plausible landslide bounds

**Several areas across the Western Ghats are processed, not one.** Running this on a
single famous disaster and reporting a hit would be choosing the answer in advance; a
scattered set of areas gives an inventory that can be used for validation.

Candidates are *candidates*. Cloud shadow, logging, quarrying and seasonal agriculture
all mimic the signature. Nothing here is a substitute for verification.

Output: data/sentinel_scars.geojson, data/sentinel_scars_summary.json

Run:  python ml_models/sentinel_inventory.py [--max-areas 5]
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.warp import Resampling, reproject
from rasterio.windows import from_bounds
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
OUT_GEOJSON = ROOT / "data" / "sentinel_scars.geojson"
OUT_SUMMARY = ROOT / "data" / "sentinel_scars_summary.json"
STAC = "https://earth-search.aws.element84.com/v1/search"

# Spread along the Western Ghats so no single event dominates the inventory.
AREAS = [
    ("wayanad",        [76.05, 11.40, 76.20, 11.55]),
    ("kozhikode",      [76.00, 11.20, 76.15, 11.35]),
    ("idukki",         [76.95,  9.85, 77.10, 10.00]),
    ("kannur",         [75.40, 12.20, 75.55, 12.35]),
    ("pathanamthitta", [76.90,  9.30, 77.05,  9.45]),
    ("palakkad",       [76.60, 10.70, 76.75, 10.85]),
]

# Dry windows either side of the 2024 monsoon.
PRE_WINDOW = ("2024-01-01T00:00:00Z", "2024-04-15T23:59:59Z")
POST_WINDOW = ("2024-11-01T00:00:00Z", "2025-03-31T23:59:59Z")

NDVI_DROP_MIN = 0.25        # loss of vegetation vigour that counts as a change
POST_NDVI_MAX = 0.45        # the ground must end up genuinely bare
MIN_SLOPE_DEG = 15.0
MIN_AREA_M2 = 900.0         # ~1 Sentinel-2 pixel block; below this is noise
MAX_AREA_M2 = 500_000.0     # above this is clearing or agriculture, not one scar
MAX_CLOUD = 15.0


def log(msg, t0=None):
    print(f"{msg}{f'  [{time.time() - t0:6.1f}s]' if t0 else ''}", flush=True)


def search(bbox, window, session, limit=8):
    body = {"collections": ["sentinel-2-l2a"], "bbox": bbox,
            "datetime": f"{window[0]}/{window[1]}",
            "query": {"eo:cloud_cover": {"lt": MAX_CLOUD}},
            "limit": limit}
    r = session.post(STAC, json=body, timeout=120)
    r.raise_for_status()
    feats = r.json().get("features", [])
    return sorted(feats, key=lambda f: f["properties"].get("eo:cloud_cover", 100))


def read_band(url, bbox, session=None):
    """Window-read a band from a remote COG.

    Reading only the area of interest keeps this to a few megabytes per band instead of
    the ~100 MB a whole Sentinel-2 tile would cost.
    """
    with rasterio.open(f"/vsicurl/{url}") as src:
        from pyproj import Transformer
        tr = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        xs, ys = tr.transform([bbox[0], bbox[2]], [bbox[1], bbox[3]])
        win = from_bounds(min(xs), min(ys), max(xs), max(ys), src.transform)
        data = src.read(1, window=win).astype(np.float32)
        transform = src.window_transform(win)
        return data, transform, src.crs


def ndvi_for(scene, bbox):
    red_url = scene["assets"]["red"]["href"]
    nir_url = scene["assets"]["nir"]["href"]
    red, transform, crs = read_band(red_url, bbox)
    nir, _, _ = read_band(nir_url, bbox)
    if red.shape != nir.shape:
        return None
    with np.errstate(invalid="ignore", divide="ignore"):
        ndvi = (nir - red) / (nir + red)
    ndvi[~np.isfinite(ndvi)] = np.nan
    return ndvi, transform, crs


def slope_on_grid(shape, transform, crs):
    """Slope from the v2 stack, resampled onto the imagery grid."""
    tile_dirs = [ROOT / "backend" / "rasters" / "v2"]
    tile_dirs += sorted((ROOT / "backend" / "rasters" / "tiles").glob("*"))
    dest = np.full(shape, np.nan, dtype=np.float32)
    for d in tile_dirs:
        p = d / "slope.tif"
        if not p.exists():
            continue
        with rasterio.open(p) as src:
            tmp = np.full(shape, np.nan, dtype=np.float32)
            reproject(source=rasterio.band(src, 1), destination=tmp,
                      dst_transform=transform, dst_crs=crs,
                      resampling=Resampling.bilinear,
                      src_nodata=src.nodata, dst_nodata=np.nan)
        dest = np.where(np.isfinite(dest), dest, tmp)
        if np.isfinite(dest).mean() > 0.98:
            break
    return dest


def polygons_from(mask, transform, res_m):
    """Connected scar patches, as centroid points with area, filtered by plausible size."""
    labels, n = ndimage.label(mask, structure=np.ones((3, 3), int))
    if n == 0:
        return []
    areas = ndimage.sum(mask, labels, index=np.arange(1, n + 1)) * res_m * res_m
    keep = np.nonzero((areas >= MIN_AREA_M2) & (areas <= MAX_AREA_M2))[0] + 1
    if keep.size == 0:
        return []
    cents = ndimage.center_of_mass(mask, labels, index=keep)
    out = []
    for (r, c), lab in zip(cents, keep):
        x, y = transform * (c + 0.5, r + 0.5)
        out.append({"x": float(x), "y": float(y),
                    "area_m2": float(areas[lab - 1])})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-areas", type=int, default=len(AREAS))
    args = ap.parse_args()
    t0 = time.time()

    session = requests.Session()
    session.headers.update({"User-Agent": "SlipSense/1.0 (landslide research)"})
    from pyproj import Transformer

    features, summary = [], []
    for name, bbox in AREAS[:args.max_areas]:
        log(f"\n=== {name} {bbox}")
        try:
            pre_scenes = search(bbox, PRE_WINDOW, session)
            post_scenes = search(bbox, POST_WINDOW, session)
        except requests.RequestException as exc:
            log(f"  search failed: {exc}")
            continue
        if not pre_scenes or not post_scenes:
            log("  no clear scene pair available")
            summary.append({"area": name, "status": "no clear pair"})
            continue

        pre, post = pre_scenes[0], post_scenes[0]
        log(f"  pre  {pre['properties']['datetime'][:10]} "
            f"cloud {pre['properties'].get('eo:cloud_cover', -1):.1f}%")
        log(f"  post {post['properties']['datetime'][:10]} "
            f"cloud {post['properties'].get('eo:cloud_cover', -1):.1f}%")

        try:
            pre_r = ndvi_for(pre, bbox)
            post_r = ndvi_for(post, bbox)
        except Exception as exc:
            log(f"  band read failed: {exc}")
            summary.append({"area": name, "status": f"read failed: {exc}"})
            continue
        if pre_r is None or post_r is None:
            summary.append({"area": name, "status": "band shape mismatch"})
            continue

        pre_ndvi, transform, crs = pre_r
        post_ndvi, post_tr, _ = post_r
        if pre_ndvi.shape != post_ndvi.shape:
            h = min(pre_ndvi.shape[0], post_ndvi.shape[0])
            w = min(pre_ndvi.shape[1], post_ndvi.shape[1])
            pre_ndvi, post_ndvi = pre_ndvi[:h, :w], post_ndvi[:h, :w]

        res_m = abs(transform.a)
        drop = pre_ndvi - post_ndvi
        slope = slope_on_grid(pre_ndvi.shape, transform, crs)

        mask = (np.isfinite(drop) & (drop >= NDVI_DROP_MIN)
                & (post_ndvi <= POST_NDVI_MAX)
                & np.isfinite(slope) & (slope >= MIN_SLOPE_DEG))
        # Remove single-pixel speckle before measuring patches.
        mask = ndimage.binary_opening(mask, np.ones((3, 3), bool))

        cands = polygons_from(mask, transform, res_m)
        to_wgs = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        for c in cands:
            lon, lat = to_wgs.transform(c["x"], c["y"])
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point",
                             "coordinates": [round(float(lon), 6), round(float(lat), 6)]},
                "properties": {
                    "area": name,
                    "area_m2": round(c["area_m2"], 1),
                    "pre_date": pre["properties"]["datetime"][:10],
                    "post_date": post["properties"]["datetime"][:10],
                    "source": "sentinel2_ndvi_change",
                    "verified": False,
                },
            })
        log(f"  {int(mask.sum()):,} changed pixels -> {len(cands)} candidate scars", t0)
        summary.append({"area": name, "status": "ok", "candidates": len(cands),
                        "pre_date": pre["properties"]["datetime"][:10],
                        "post_date": post["properties"]["datetime"][:10],
                        "changed_pixels": int(mask.sum())})

    OUT_GEOJSON.write_text(json.dumps(
        {"type": "FeatureCollection", "features": features}))
    OUT_SUMMARY.write_text(json.dumps({
        "areas": summary, "total_candidates": len(features),
        "criteria": {"ndvi_drop_min": NDVI_DROP_MIN, "post_ndvi_max": POST_NDVI_MAX,
                     "min_slope_deg": MIN_SLOPE_DEG,
                     "min_area_m2": MIN_AREA_M2, "max_area_m2": MAX_AREA_M2},
        "caveat": "Unverified candidates. NDVI loss on steep ground is also produced by "
                  "logging, quarrying, cloud shadow and seasonal agriculture.",
    }, indent=2))

    log(f"\nTotal candidate scars: {len(features)} across "
        f"{sum(1 for s in summary if s.get('status') == 'ok')} areas")
    log(f"Wrote {OUT_GEOJSON.relative_to(ROOT)}")
    log("Done.", t0)


if __name__ == "__main__":
    main()
