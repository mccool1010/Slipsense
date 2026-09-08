"""
generate_runout_v2.py
Produce runout hazard layers from the corrected v2 stack.

Replaces generate_runout_and_fuse.py. That script consumed `DEM_filled_75.tif` as
elevation (it holds slope in degrees) and `slope75.tif` as slope (pinned at 83-90
degrees), so it routed debris across the wrong surface and its deposition rule could
never fire. It also read `susceptibility_dl.tif`, the map that ranked real landslides at
percentile 41.

Sources are seeded from the calibrated susceptibility thresholds rather than a
hand-picked 0.80, so the runout inherits the same selectivity as the alert tiers.

Outputs, all on the v2 grid:
  runout_flux.tif        relative debris throughput per cell
  runout_velocity.tif    modelled velocity, m/s
  runout_energy.tif      energy height, m
  transit_mask.tif       cells debris passes through
  deposition_mask.tif    cells where debris comes to rest
  hazard_fused.tif       zone code: 0 none, 1 deposition, 2 transit, 3 source
  runout_paths.geojson   centreline corridors with length, drop, velocity, energy

Run:  python ml_models/generate_runout_v2.py [--threshold 0.704] [--reach 22]
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).parent))
import runout as runout_model  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "backend" / "rasters" / "v2"

ZONE_NONE, ZONE_DEPOSITION, ZONE_TRANSIT, ZONE_SOURCE = 0, 1, 2, 3


def log(msg, t0=None):
    print(f"{msg}{f'  [{time.time() - t0:6.1f}s]' if t0 else ''}", flush=True)


def read(name, stack=V2):
    with rasterio.open(stack / f"{name}.tif") as src:
        return src.read(1).astype(np.float64), src.profile.copy(), src.transform


def write(path, data, profile, dtype="float32"):
    p = profile.copy()
    p.update(dtype=dtype, count=1, compress="lzw",
             nodata=np.nan if dtype == "float32" else 255)
    with rasterio.open(path, "w", **p) as dst:
        dst.write(np.asarray(data, dtype=dtype), 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", type=Path, default=V2)
    ap.add_argument("--threshold", type=float, default=0.704,
                    help="susceptibility for a source cell (default: the HIGH tier)")
    ap.add_argument("--reach", type=float, default=22.0,
                    help="angle of reach in degrees; lower travels further")
    ap.add_argument("--spread", type=float, default=4.0,
                    help="Holmgren spreading exponent")
    ap.add_argument("--min-slope", type=float, default=15.0,
                    help="minimum slope for a source cell")
    ap.add_argument("--max-paths", type=int, default=400)
    args = ap.parse_args()

    stack = args.stack
    t0 = time.time()

    dem, profile, transform = read("elevation", stack)
    slope, _, _ = read("slope", stack)
    sus_path = stack / "susceptibility_ml.tif"
    if not sus_path.exists():
        raise SystemExit(f"Missing {sus_path}. Run generate_susceptibility_v2.py first.")
    with rasterio.open(sus_path) as src:
        sus = src.read(1).astype(np.float64)

    nodata = ~np.isfinite(dem)
    log(f"Grid {dem.shape[0]}x{dem.shape[1]}, {100 * (~nodata).mean():.1f}% valid")

    sources = runout_model.source_cells(sus, args.threshold, slope, args.min_slope)
    log(f"Source cells: {int(sources.sum()):,} "
        f"({100 * sources.mean():.3f}% of grid) at susceptibility >= {args.threshold} "
        f"and slope >= {args.min_slope} deg")
    if not sources.any():
        raise SystemExit("No source cells - lower --threshold or --min-slope.")

    log(f"Propagating (reach angle {args.reach} deg, spread exponent {args.spread}) ...")
    result = runout_model.propagate(
        dem, sources, source_strength=sus, res=abs(transform.a),
        reach_angle_deg=args.reach, spread_exponent=args.spread, nodata_mask=nodata,
    )
    log("  done", t0)

    transit, deposition = result["transit"], result["deposition"]
    vel = result["velocity"]
    log(f"  transit cells    {int(transit.sum()):,} ({100 * transit.mean():.2f}% of grid)")
    log(f"  deposition cells {int(deposition.sum()):,}")
    finite_v = vel[np.isfinite(vel) & (vel > 0)]
    if finite_v.size:
        log(f"  velocity  median {np.median(finite_v):.1f} m/s  "
            f"p95 {np.percentile(finite_v, 95):.1f}  max {finite_v.max():.1f}")

    zones = np.full(dem.shape, ZONE_NONE, dtype=np.uint8)
    zones[deposition] = ZONE_DEPOSITION
    zones[transit & ~deposition] = ZONE_TRANSIT
    zones[sources] = ZONE_SOURCE
    zones[nodata] = 255

    log("Writing rasters ...")
    write(stack / "runout_flux.tif", result["flux"], profile)
    write(stack / "runout_velocity.tif", vel, profile)
    write(stack / "runout_energy.tif", result["energy_height"], profile)
    write(stack / "transit_mask.tif", transit.astype(np.float32), profile)
    write(stack / "deposition_mask.tif", deposition.astype(np.float32), profile)
    write(stack / "hazard_fused.tif", zones, profile, dtype="uint8")

    log(f"Tracing centreline corridors (max {args.max_paths}) ...")
    paths = runout_model.trace_paths(
        dem, np.nan_to_num(result["flux"]), sources,
        energy=np.nan_to_num(result["energy_height"]), res=abs(transform.a),
        max_paths=args.max_paths, nodata_mask=nodata,
    )
    log(f"  {len(paths)} paths", t0)

    # GeoJSON must be WGS84 lon/lat. RFC 7946 removed the `crs` member entirely, and
    # Leaflet ignores it, so writing projected metres here puts every corridor tens of
    # thousands of degrees off the map - which is exactly what happened when this file
    # was first written in EPSG:32643.
    to_wgs = Transformer.from_crs(profile["crs"], "EPSG:4326", always_xy=True)

    features = []
    for pts in paths:
        coords, vels = [], []
        for r, c in pts:
            x, y = transform * (c + 0.5, r + 0.5)
            lon, lat = to_wgs.transform(x, y)
            coords.append([round(float(lon), 6), round(float(lat), 6)])
            v = vel[r, c]
            if np.isfinite(v):
                vels.append(float(v))
        r0, c0 = pts[0]
        r1, c1 = pts[-1]
        drop = float(dem[r0, c0] - dem[r1, c1])
        length = float(len(pts) * abs(transform.a))
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "length_m": round(length, 1),
                "drop_m": round(drop, 1),
                # Overall angle of reach actually achieved by this corridor.
                "reach_angle_deg": round(float(np.degrees(np.arctan2(drop, length))), 2)
                if length > 0 else None,
                "max_velocity_ms": round(max(vels), 1) if vels else None,
                "mean_velocity_ms": round(float(np.mean(vels)), 1) if vels else None,
                "source_susceptibility": round(float(sus[r0, c0]), 3),
            },
        })

    # No `crs` member: RFC 7946 defines GeoJSON as WGS84 and removed it. Declaring one
    # gave false reassurance while consumers silently assumed degrees.
    geojson = {"type": "FeatureCollection", "features": features}
    out_geojson = stack / "runout_paths.geojson"
    out_geojson.write_text(json.dumps(geojson))
    log(f"Wrote {out_geojson.relative_to(ROOT)}")

    if features:
        lens = [f["properties"]["length_m"] for f in features]
        angles = [f["properties"]["reach_angle_deg"] for f in features
                  if f["properties"]["reach_angle_deg"] is not None]
        log(f"  corridor length  median {np.median(lens):.0f} m  max {max(lens):.0f} m")
        if angles:
            log(f"  achieved reach angle  median {np.median(angles):.1f} deg")
    log("Done.", t0)


if __name__ == "__main__":
    main()
