"""
build_soil_layer.py
Real soil properties for the terrain stack, from SoilGrids at 250 m.

The soil layer already in the repository (`soil_susceptibility_index.tif`) derives from
a **30 x 29 pixel** source - roughly 5 km per cell, giving about 22 distinct values
across a 110 km tile. At that resolution it varies far more slowly than the terrain it
is meant to modulate, so it was excluded from the model as unusable. Soil is one of the
strongest physical controls on shallow failure, and leaving it out is a real gap.

SoilGrids (ISRIC) serves global predictions at 250 m over WCS, no key required. That is
still coarser than the 30 m terrain grid, but it is ~60x finer than what was there and
resolves genuine catchment-scale variation.

Properties fetched, and why each matters:
  clay   plastic, water-retaining; high clay holds pore pressure and loses strength wet
  sand   free-draining; dissipates pore pressure quickly
  bdod   bulk density, a proxy for compaction and for the weight driving failure
  cfvo   coarse fragments, which add frictional strength
  soc    organic carbon, concentrated in the rooted horizon that binds the soil mantle

Output: backend/rasters/v2/soil_clay.tif, soil_sand.tif, soil_bdod.tif,
        soil_cfvo.tif, soil_soc.tif, soil_index.tif

Run:  python ml_models/build_soil_layer.py
"""

import argparse
import time
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.warp import Resampling, reproject

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "backend" / "rasters" / "v2"
CACHE = ROOT / "data" / "soilgrids"
WCS = "https://maps.isric.org/mapserv"

# property -> (map file, coverage id, scale factor to real units)
PROPERTIES = {
    "clay": ("clay", "clay_0-5cm_mean", 0.1),    # g/kg -> %
    "sand": ("sand", "sand_0-5cm_mean", 0.1),    # g/kg -> %
    "bdod": ("bdod", "bdod_0-5cm_mean", 0.01),   # cg/cm3 -> g/cm3
    "cfvo": ("cfvo", "cfvo_0-5cm_mean", 0.1),    # cm3/dm3 -> %
    "soc":  ("soc", "soc_0-5cm_mean", 0.1),      # dg/kg -> g/kg
}


def log(msg, t0=None):
    print(f"{msg}{f'  [{time.time() - t0:6.1f}s]' if t0 else ''}", flush=True)


def fetch(prop, mapfile, coverage, bounds_wgs, session):
    """Download one SoilGrids coverage for the tile bounds."""
    CACHE.mkdir(parents=True, exist_ok=True)
    # Key the cache on the bounds as well as the coverage: the same coverage id is
    # requested for every tile, and keying on the name alone would hand tile 2 the
    # subset downloaded for tile 1.
    tag = "_".join(f"{v:.2f}" for v in bounds_wgs)
    out = CACHE / f"{coverage}_{tag}.tif"
    if out.exists() and out.stat().st_size > 10_000:
        return out

    west, south, east, north = bounds_wgs
    params = {
        "map": f"/map/{mapfile}.map", "SERVICE": "WCS", "VERSION": "2.0.1",
        "REQUEST": "GetCoverage", "COVERAGEID": coverage,
        "FORMAT": "GEOTIFF_INT16",
        "SUBSET": [f"X({west},{east})", f"Y({south},{north})"],
        "SUBSETTINGCRS": "http://www.opengis.net/def/crs/EPSG/0/4326",
        "OUTPUTCRS": "http://www.opengis.net/def/crs/EPSG/0/4326",
    }
    for attempt in range(4):
        try:
            r = session.get(WCS, params=params, timeout=180)
            r.raise_for_status()
            if len(r.content) < 5_000:
                raise requests.RequestException("suspiciously small response")
            out.write_bytes(r.content)
            return out
        except requests.RequestException as exc:
            log(f"    attempt {attempt + 1} failed: {exc}")
            time.sleep(8 * (attempt + 1))
    raise RuntimeError(f"could not fetch {coverage}")


def main():
    # `global` must precede any use of the name in this scope, including the argparse
    # default below.
    global V2
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", type=Path, default=V2,
                    help="terrain stack directory to build layers into")
    args = ap.parse_args()
    V2 = args.stack
    t0 = time.time()
    with rasterio.open(V2 / "elevation.tif") as src:
        profile = src.profile.copy()
        dst_crs, dst_transform = src.crs, src.transform
        h, w = src.height, src.width
        nodata = ~np.isfinite(src.read(1))
        bounds = src.bounds

    from pyproj import Transformer
    to_wgs = Transformer.from_crs(dst_crs, "EPSG:4326", always_xy=True)
    xs = [bounds.left, bounds.right, bounds.left, bounds.right]
    ys = [bounds.bottom, bounds.bottom, bounds.top, bounds.top]
    lon, lat = to_wgs.transform(xs, ys)
    # Pad so reprojection has data at the edges rather than sampling off the coverage.
    bounds_wgs = (min(lon) - 0.05, min(lat) - 0.05, max(lon) + 0.05, max(lat) + 0.05)
    log(f"Tile bounds (WGS84): {[round(b, 3) for b in bounds_wgs]}")

    session = requests.Session()
    session.headers.update({"User-Agent": "SlipSense/1.0 (landslide research)"})

    out_profile = profile.copy()
    out_profile.update(dtype="float32", count=1, nodata=np.nan, compress="lzw")
    layers = {}

    for prop, (mapfile, coverage, scale) in PROPERTIES.items():
        log(f"Fetching {coverage} ...")
        path = fetch(prop, mapfile, coverage, bounds_wgs, session)

        dest = np.full((h, w), np.nan, dtype=np.float32)
        with rasterio.open(path) as src:
            band = src.read(1).astype(np.float32)
            # SoilGrids uses a large negative sentinel for no data.
            band[band <= -32000] = np.nan
            band *= scale
            reproject(
                source=band, destination=dest,
                src_transform=src.transform, src_crs=src.crs,
                dst_transform=dst_transform, dst_crs=dst_crs,
                resampling=Resampling.bilinear,
                src_nodata=np.nan, dst_nodata=np.nan,
            )
        dest[nodata] = np.nan
        layers[prop] = dest

        with rasterio.open(V2 / f"soil_{prop}.tif", "w", **out_profile) as dst:
            dst.write(dest, 1)
        finite = dest[np.isfinite(dest)]
        log(f"  soil_{prop}.tif  min {finite.min():7.2f}  med {np.median(finite):7.2f}  "
            f"max {finite.max():7.2f}", t0)

    # A composite index, so a single feature can carry soil where model parsimony
    # matters. Clay raises susceptibility (retains water, loses strength when wet);
    # sand and coarse fragments lower it (drain freely, add friction).
    def norm(a):
        f = a[np.isfinite(a)]
        if f.size == 0:
            return np.zeros_like(a)
        lo, hi = np.percentile(f, [2, 98])
        return np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1)

    index = (0.5 * norm(layers["clay"])
             + 0.2 * (1.0 - norm(layers["sand"]))
             + 0.2 * (1.0 - norm(layers["cfvo"]))
             + 0.1 * norm(layers["bdod"]))
    index = np.where(nodata, np.nan, index).astype(np.float32)
    with rasterio.open(V2 / "soil_index.tif", "w", **out_profile) as dst:
        dst.write(index, 1)
    finite = index[np.isfinite(index)]
    log(f"\n  soil_index.tif  min {finite.min():.3f}  med {np.median(finite):.3f}  "
        f"max {finite.max():.3f}")
    log(f"  distinct values: {len(np.unique(np.round(finite, 3))):,} "
        f"(the layer this replaces had ~22 across the whole tile)")
    log("Done.", t0)


if __name__ == "__main__":
    main()
