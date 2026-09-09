"""
build_landcover_layer.py
Land cover and vegetation from ESA WorldCover 10 m.

Vegetation is the missing anthropogenic control in this feature set. Root systems
reinforce the soil mantle, and losing them is repeatedly implicated in Western Ghats
failures: conversion of forest to plantation or bare ground removes reinforcement on
exactly the steep slopes that are marginal to begin with. A model built only from
terrain cannot see any of that, and it cannot distinguish two identical hillsides where
one is forested and the other has been cleared.

ESA WorldCover 2021 v200 is free, needs no key, and is served as 3x3 degree COGs from
AWS at 10 m - finer than our 30 m analysis grid, so classes are aggregated by taking
the fraction of each 30 m cell occupied by the relevant class rather than by nearest
neighbour, which would throw away most of the detail.

Layers produced:
  landcover.tif        dominant WorldCover class per 30 m cell
  forest_fraction.tif  share of the cell under tree cover - the reinforcement proxy
  bare_fraction.tif    share bare or sparsely vegetated - the exposure proxy
  crop_fraction.tif    share under cropland/plantation

Run:  python ml_models/build_landcover_layer.py
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
CACHE = ROOT / "data" / "worldcover"
BASE = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
        "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif")

# WorldCover class codes
TREE, SHRUB, GRASS, CROP, BUILT, BARE, SNOW, WATER, WETLAND, MANGROVE, MOSS = (
    10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100)


def log(msg, t0=None):
    print(f"{msg}{f'  [{time.time() - t0:6.1f}s]' if t0 else ''}", flush=True)


def tile_name(lat, lon):
    """WorldCover tiles are named by the 3-degree cell they start at."""
    la = int(np.floor(lat / 3.0) * 3)
    lo = int(np.floor(lon / 3.0) * 3)
    return f"{'S' if la < 0 else 'N'}{abs(la):02d}{'W' if lo < 0 else 'E'}{abs(lo):03d}"


def fetch(tile, session):
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / f"{tile}.tif"
    if out.exists() and out.stat().st_size > 1_000_000:
        return out
    url = BASE.format(tile=tile)
    log(f"  downloading {tile} ...")
    with session.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(out, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    return out


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
    lon, lat = to_wgs.transform(
        [bounds.left, bounds.right, bounds.left, bounds.right],
        [bounds.bottom, bounds.bottom, bounds.top, bounds.top])

    tiles = sorted({tile_name(la, lo)
                    for la in (min(lat), max(lat)) for lo in (min(lon), max(lon))})
    log(f"WorldCover tiles needed: {tiles}")

    session = requests.Session()
    session.headers.update({"User-Agent": "SlipSense/1.0 (landslide research)"})
    paths = [fetch(t, session) for t in tiles]
    log("Downloads complete", t0)

    # Fractional cover: reproject a 0/1 mask per class with area-weighted averaging, so
    # a 30 m cell reports the share it contains rather than whichever 10 m pixel happens
    # to land at its centre.
    fractions = {}
    for name, codes in (("forest", (TREE,)), ("bare", (BARE, MOSS)),
                        ("crop", (CROP, SHRUB, GRASS))):
        acc = np.zeros((h, w), dtype=np.float32)
        for path in paths:
            with rasterio.open(path) as src:
                block = src.read(1)
                mask = np.isin(block, codes).astype(np.float32)
                dest = np.zeros((h, w), dtype=np.float32)
                reproject(
                    source=mask, destination=dest,
                    src_transform=src.transform, src_crs=src.crs,
                    dst_transform=dst_transform, dst_crs=dst_crs,
                    resampling=Resampling.average,
                    src_nodata=None, dst_nodata=0.0,
                )
            acc = np.maximum(acc, dest)
        acc[nodata] = np.nan
        fractions[name] = acc
        log(f"  {name}_fraction: mean {np.nanmean(acc):.3f}")

    dominant = np.zeros((h, w), dtype=np.float32)
    for path in paths:
        with rasterio.open(path) as src:
            dest = np.zeros((h, w), dtype=np.float32)
            reproject(
                source=src.read(1).astype(np.float32), destination=dest,
                src_transform=src.transform, src_crs=src.crs,
                dst_transform=dst_transform, dst_crs=dst_crs,
                resampling=Resampling.mode, src_nodata=0, dst_nodata=0,
            )
        dominant = np.where(dest > 0, dest, dominant)
    dominant[nodata] = np.nan

    out_profile = profile.copy()
    out_profile.update(dtype="float32", count=1, nodata=np.nan, compress="lzw")
    for name, arr in (("landcover", dominant),
                      ("forest_fraction", fractions["forest"]),
                      ("bare_fraction", fractions["bare"]),
                      ("crop_fraction", fractions["crop"])):
        with rasterio.open(V2 / f"{name}.tif", "w", **out_profile) as dst:
            dst.write(np.asarray(arr, dtype=np.float32), 1)
        log(f"  wrote {name}.tif")

    valid = np.isfinite(dominant)
    codes, counts = np.unique(dominant[valid].astype(int), return_counts=True)
    names = {TREE: "tree cover", SHRUB: "shrubland", GRASS: "grassland",
             CROP: "cropland", BUILT: "built-up", BARE: "bare/sparse",
             WATER: "water", WETLAND: "wetland", MANGROVE: "mangrove", MOSS: "moss"}
    log("\nLand cover composition:")
    for c, n in sorted(zip(codes, counts), key=lambda t: -t[1])[:8]:
        log(f"  {names.get(int(c), f'class {int(c)}'):16s} {100 * n / counts.sum():5.2f}%")
    log("Done.", t0)


if __name__ == "__main__":
    main()
