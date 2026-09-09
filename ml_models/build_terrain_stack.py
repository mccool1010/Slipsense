"""
build_terrain_stack.py
Regenerate the full terrain feature stack from a clean Copernicus GLO-30 DEM.

Writes to backend/rasters/v2/ so the broken originals stay untouched until the new
stack has been validated. Every layer is produced in EPSG:32643 (UTM 43N, metres) on
one shared grid, which is what the old stack lacked: it mixed EPSG:4326 and EPSG:32643
layers and computed slope in degrees-as-horizontal-units.

Run:  python ml_models/build_terrain_stack.py
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import rasterio

sys.path.insert(0, str(Path(__file__).parent))
import terrain  # noqa: E402
# geo_io reader retained for other inventories; streams now come from flow accumulation

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEM = ROOT / "data" / "dem" / "cop30_N12_E075.tif"
DEFAULT_OUT = ROOT / "backend" / "rasters" / "v2"
# River_Vectors.shp is deliberately unused: see terrain.streams_from_accumulation


def log(msg, t0=None):
    stamp = f"  [{time.time() - t0:6.1f}s]" if t0 else ""
    print(f"{msg}{stamp}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dem", type=Path, default=DEFAULT_DEM,
                    help="source DEM tile in geographic coordinates")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help="directory to write the terrain layers into")
    args = ap.parse_args()

    dem_src, out_dir = args.dem, args.out
    dem_utm = dem_src.with_name(dem_src.stem + "_utm.tif")

    t0 = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not dem_src.exists():
        raise FileNotFoundError(f"DEM not downloaded yet: {dem_src}")

    log(f"Reprojecting {dem_src.name} to EPSG:32643 @ 30 m ...")
    terrain.reproject_dem(dem_src, dem_utm)

    with rasterio.open(dem_utm) as src:
        dem = src.read(1).astype(np.float64)
        profile = src.profile.copy()
        transform = src.transform
    nodata = ~np.isfinite(dem)
    log(f"  grid {dem.shape[0]}x{dem.shape[1]}, "
        f"{100 * (~nodata).mean():.1f}% valid, "
        f"elev {np.nanmin(dem):.0f}-{np.nanmax(dem):.0f} m", t0)

    # Priority-Flood needs finite values everywhere; nodata is masked out separately.
    dem_work = np.where(nodata, np.nanmax(dem), dem)

    log("Filling depressions (Priority-Flood) ...")
    filled = terrain.fill_depressions(dem_work, nodata)
    raised = float(np.nansum(filled - dem_work))
    log(f"  filled, total elevation added {raised:.0f} m-cells", t0)

    log("Slope and aspect (Horn) ...")
    slope, aspect, _, _ = terrain.slope_aspect(filled)
    log(f"  slope {np.nanmin(slope):.1f}-{np.nanmax(slope):.1f} deg, "
        f"mean {np.nanmean(slope[~nodata]):.1f}", t0)

    log("Curvature (Zevenbergen-Thorne) ...")
    plan, prof = terrain.curvature(filled)

    log("D8 flow accumulation ...")
    acc = terrain.flow_accumulation(filled, nodata)
    log(f"  max accumulation {np.nanmax(acc):.0f} cells", t0)

    log("TWI and SPI ...")
    twi, spi = terrain.wetness_indices(acc, slope)

    log("Stream network, river distance and drainage density ...")
    river_mask = terrain.streams_from_accumulation(acc, nodata)
    log(f"  {int(river_mask.sum())} stream cells "
        f"({100 * river_mask.mean():.2f}% of grid)")
    dist_river = terrain.distance_to(river_mask)
    drainage = terrain.density(river_mask)

    log("Relative relief ...")
    relief = terrain.relative_relief(filled)

    layers = {
        "elevation": filled,
        "slope": slope,
        "aspect": aspect,
        "plan_curvature": plan,
        "profile_curvature": prof,
        "flow_acc": np.log1p(acc),      # raw accumulation spans 5 orders of magnitude
        "twi": twi,
        "spi": spi,
        "dist_river": dist_river,
        "drainage_density": drainage,
        "relative_relief": relief,
    }

    log("Writing layers ...")
    for name, arr in layers.items():
        out = np.asarray(arr, dtype=np.float32)
        out[nodata] = np.nan
        terrain.write_like(out_dir / f"{name}.tif", out, profile)
        finite = out[np.isfinite(out)]
        log(f"  {name:19s} min {finite.min():10.2f}  med {np.median(finite):10.2f}  "
            f"max {finite.max():10.2f}")

    log(f"\nDone. {len(layers)} layers in {out_dir.relative_to(ROOT)}", t0)


if __name__ == "__main__":
    main()
