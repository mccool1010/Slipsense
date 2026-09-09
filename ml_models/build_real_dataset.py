"""
build_real_dataset.py
Build a landslide training dataset from the real inventory and the real terrain rasters.

This replaces data_preparation.py, which fabricated 69% of its rows with
np.random.uniform and generated `elevation`/`dist_river` conditional on the label
(a direct leak: `dist_river < 1250` separated its synthetic rows perfectly).

Every row written here is a real coordinate sampled against real rasters:
  positives  - the 279-point landslide inventory (Landslides.shp, EPSG:32643)
  negatives  - random terrain locations at least BUFFER_M from any known landslide,
               kept only where every feature raster has valid data

Sampling is done per-raster in that raster's own CRS. The old code passed lon/lat
into EPSG:32643 rasters, which lands far out of bounds and returns NaN for every UTM
layer - the reason the Global Landslide Catalog extraction silently failed and fell
back to inventing 50 random positives.

Output: data/real_landslide_dataset.csv (x, y retained so training can do spatial CV)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
from geo_io import read_points  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RASTERS = ROOT / "backend" / "rasters"

INVENTORY = ROOT / "Landslides.shp"
INVENTORY_CRS = "EPSG:32643"          # WGS84 / UTM zone 43N, from Landslides.prj
OUTPUT = ROOT / "data" / "real_landslide_dataset.csv"

BUFFER_M = 500        # negatives must be at least this far from any mapped landslide
NEG_POOL = 2500       # size of the negative pool to write (training subsamples it)
SEED = 42

# Feature name -> raster path. Mixed CRS is handled per-raster at sample time.
# The v2 stack is rebuilt by build_terrain_stack.py from a clean Copernicus GLO-30 DEM;
# the originals it replaces were mislabelled (DEM_filled_75.tif held slope, slope75.tif
# was computed in degrees-as-metres and pinned at 83-90, Distance_to_River was binary).
V2 = RASTERS / "v2"
FEATURE_RASTERS = {
    "elevation":           V2 / "elevation.tif",
    "slope":               V2 / "slope.tif",
    "aspect":              V2 / "aspect.tif",
    "plan_curvature":      V2 / "plan_curvature.tif",
    "profile_curvature":   V2 / "profile_curvature.tif",
    "twi":                 V2 / "twi.tif",
    "spi":                 V2 / "spi.tif",
    "flow_acc":            V2 / "flow_acc.tif",
    "dist_river":          V2 / "dist_river.tif",
    "drainage_density":    V2 / "drainage_density.tif",
    "relative_relief":     V2 / "relative_relief.tif",
}

# Layers added later, included only when built. Keeping them optional means the core
# terrain dataset still builds on a clean checkout before the download steps have run.
#
# dist_road is here for two reasons. Road cuts genuinely destabilise slopes by removing
# toe support. It is also the sharpest test of the inventory-bias hypothesis: the
# baseline comparison found the model beating relative relief on its own inventory but
# not on independent events, which is what you would see if the 279 points were mapped
# preferentially along accessible ground. If dist_road dominates the importances, that
# is direct evidence the model is partly learning where landslides get *recorded*.
OPTIONAL_RASTERS = {
    "dist_road":       V2 / "dist_road.tif",
    "soil_clay":       V2 / "soil_clay.tif",
    "soil_sand":       V2 / "soil_sand.tif",
    "soil_index":      V2 / "soil_index.tif",
    "forest_fraction": V2 / "forest_fraction.tif",
    "bare_fraction":   V2 / "bare_fraction.tif",
}
for _name, _path in OPTIONAL_RASTERS.items():
    if _path.exists():
        FEATURE_RASTERS[_name] = _path

# Values that mean "no data" but are not always declared in the raster profile.
SENTINELS = (-9999.0, -99999.0, -3.4028234663852886e38)


def sample_raster(path, xs, ys, src_crs=INVENTORY_CRS):
    """Sample one raster at (xs, ys) given in src_crs, returning NaN where invalid."""
    with rasterio.open(path) as src:
        if src.crs is None:
            raise ValueError(f"{path.name} has no CRS")
        if str(src.crs) != str(src_crs):
            tr = Transformer.from_crs(src_crs, src.crs, always_xy=True)
            rx, ry = tr.transform(xs, ys)
        else:
            rx, ry = np.asarray(xs), np.asarray(ys)

        out = np.full(len(xs), np.nan, dtype=float)
        left, bottom, right, top = src.bounds
        inside = (rx >= left) & (rx <= right) & (ry >= bottom) & (ry <= top)
        if inside.any():
            vals = np.array(
                [v[0] for v in src.sample(np.column_stack([rx[inside], ry[inside]]), 1)],
                dtype=float,
            )
            if src.nodata is not None:
                vals[vals == src.nodata] = np.nan
            for s in SENTINELS:
                vals[np.isclose(vals, s, rtol=1e-6)] = np.nan
            out[inside] = vals
    return out


def sample_all(xs, ys):
    """Sample every feature raster at the given coordinates."""
    return {name: sample_raster(p, xs, ys) for name, p in FEATURE_RASTERS.items()}


def reference_extent():
    """Bounding box (in INVENTORY_CRS) shared by the UTM terrain stack."""
    with rasterio.open(FEATURE_RASTERS["relative_relief"]) as src:
        return src.bounds


def build_negatives(pos_xy, n_target, rng):
    """Draw random valid terrain points outside the landslide buffer."""
    left, bottom, right, top = reference_extent()
    tree = cKDTree(pos_xy)

    kept_x, kept_y, kept_feats = [], [], []
    attempts, batch = 0, max(n_target * 4, 4000)

    while sum(len(a) for a in kept_x) < n_target and attempts < 40:
        attempts += 1
        cx = rng.uniform(left, right, batch)
        cy = rng.uniform(bottom, top, batch)

        far = tree.query(np.column_stack([cx, cy]))[0] >= BUFFER_M
        cx, cy = cx[far], cy[far]
        if len(cx) == 0:
            continue

        feats = sample_all(cx, cy)
        good = np.ones(len(cx), dtype=bool)
        for v in feats.values():
            good &= np.isfinite(v)
        if not good.any():
            continue

        kept_x.append(cx[good])
        kept_y.append(cy[good])
        kept_feats.append({k: v[good] for k, v in feats.items()})
        print(f"  attempt {attempts}: +{int(good.sum())} valid "
              f"(total {sum(len(a) for a in kept_x)})", flush=True)

    if not kept_x:
        raise RuntimeError("Could not sample any valid negative locations")

    xs = np.concatenate(kept_x)[:n_target]
    ys = np.concatenate(kept_y)[:n_target]
    feats = {
        k: np.concatenate([f[k] for f in kept_feats])[:n_target]
        for k in FEATURE_RASTERS
    }
    return xs, ys, feats


def main():
    rng = np.random.default_rng(SEED)
    print("=" * 64)
    print("Building real landslide dataset (no synthetic rows)")
    print("=" * 64)

    for name, path in FEATURE_RASTERS.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing raster for '{name}': {path}")

    pos = read_points(INVENTORY)
    print(f"\nInventory: {len(pos)} landslide points from {INVENTORY.name} ({INVENTORY_CRS})")

    print("\nSampling positives...")
    pos_feats = sample_all(pos[:, 0], pos[:, 1])
    pos_ok = np.ones(len(pos), dtype=bool)
    for name, v in pos_feats.items():
        missing = ~np.isfinite(v)
        if missing.any():
            print(f"  {name:22s} {int(missing.sum())} of {len(pos)} points have no data")
        pos_ok &= np.isfinite(v)
    print(f"  {int(pos_ok.sum())} of {len(pos)} positives have a complete feature vector")

    pos_xy = pos[pos_ok]
    pos_feats = {k: v[pos_ok] for k, v in pos_feats.items()}

    print(f"\nSampling negatives (at least {BUFFER_M} m from any landslide, target {NEG_POOL})...")
    neg_x, neg_y, neg_feats = build_negatives(pos_xy, NEG_POOL, rng)
    print(f"  kept {len(neg_x)} negatives")

    rows = {"x": np.concatenate([pos_xy[:, 0], neg_x]),
            "y": np.concatenate([pos_xy[:, 1], neg_y])}
    for name in FEATURE_RASTERS:
        rows[name] = np.concatenate([pos_feats[name], neg_feats[name]])
    rows["landslide"] = np.concatenate([
        np.ones(len(pos_xy), dtype=int), np.zeros(len(neg_x), dtype=int)
    ])

    df = pd.DataFrame(rows)

    # Aspect is circular: 359 deg and 1 deg are neighbours, but a tree split at 180
    # treats them as opposites. Decompose into northness/eastness so the geometry survives.
    rad = np.deg2rad(df["aspect"].where(df["aspect"] >= 0))
    df["aspect_north"] = np.cos(rad).fillna(0.0)
    df["aspect_east"] = np.sin(rad).fillna(0.0)

    # WGS84 lon/lat alongside UTM, for mapping and for joining external datasets.
    tr = Transformer.from_crs(INVENTORY_CRS, "EPSG:4326", always_xy=True)
    df["lon"], df["lat"] = tr.transform(df["x"].values, df["y"].values)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT, index=False)

    print("\n" + "=" * 64)
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    print(f"  rows      : {len(df)}  ({int(df.landslide.sum())} positive, "
          f"{int((df.landslide == 0).sum())} negative)")
    print(f"  features  : {len(FEATURE_RASTERS) + 2} (incl. aspect_north/aspect_east)")
    print(f"  synthetic : 0")
    print("=" * 64)

    with pd.option_context("display.width", 140, "display.max_columns", 30):
        print("\nFeature means by class:")
        print(df.groupby("landslide")[list(FEATURE_RASTERS)].mean().T.to_string())

    return df


if __name__ == "__main__":
    main()
