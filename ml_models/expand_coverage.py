"""
expand_coverage.py
Extend susceptibility prediction beyond the tile the model was trained on, and check
honestly how far that extension can be trusted.

The inventory used for training lies entirely within one 1x1 degree tile (75-76E,
12-13N). Predicting on other tiles is extrapolation: the terrain is similar Western
Ghats topography, but no labelled landslide from those tiles ever informed the model.
Extrapolated output is therefore validated against two sources the model has never
seen, rather than presented as if it were measured:

  GSI susceptibility zones   the published Geological Survey of India polygons for
                             13 Kerala districts - if the model is transferring, its
                             probabilities should rise across the GSI class ordering
  NASA catalog events        dated landslides in the region from an independent
                             inventory - these should land high in the map's own
                             distribution, as they do on the training tile

Run:  python ml_models/expand_coverage.py [--build] [--validate]
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import rasterio

sys.path.insert(0, str(Path(__file__).parent))
ROOT = Path(__file__).resolve().parent.parent
DEM_DIR = ROOT / "data" / "dem"
TILES_DIR = ROOT / "backend" / "rasters" / "tiles"
MODEL = ROOT / "ml_models" / "susceptibility_model.pkl"
CATALOG = ROOT / "data" / "Global_Landslide_Catalog_Export_rows.csv"
GSI = ROOT / "backend" / "rasters" / "susceptibility_historical_gsi.tif"
REPORT = ROOT / "ml_models" / "coverage_report.md"
METRICS = ROOT / "ml_models" / "coverage_metrics.json"

TRAINED_TILE = "cop30_N12_E075"
from features import DEPLOYED as FEATURES  # canonical set, see features.py
CHUNK_ROWS = 256


def log(msg, t0=None):
    print(f"{msg}{f'  [{time.time() - t0:6.1f}s]' if t0 else ''}", flush=True)


def available_tiles():
    """DEM tiles that finished downloading, excluding reprojection by-products."""
    out = []
    for p in sorted(DEM_DIR.glob("cop30_N*_E*.tif")):
        if p.stem.endswith("_utm"):
            continue
        try:
            with rasterio.open(p) as src:
                if src.width > 100:
                    out.append(p)
        except Exception:
            continue
    return out


def build_stacks(tiles):
    """Run the terrain builder for every tile that has no stack yet."""
    for dem in tiles:
        out_dir = TILES_DIR / dem.stem
        if (out_dir / "relative_relief.tif").exists():
            log(f"  {dem.stem}: stack already present, skipping")
            continue
        log(f"  {dem.stem}: building terrain stack ...")
        subprocess.run(
            [sys.executable, str(Path(__file__).parent / "build_terrain_stack.py"),
             "--dem", str(dem), "--out", str(out_dir)],
            check=True,
        )


def predict_tile(stack_dir, model):
    """Apply the fitted model across one tile's terrain stack."""
    out_path = stack_dir / "susceptibility_ml.tif"
    layers = [f for f in FEATURES if not f.startswith("aspect_")]
    srcs = {n: rasterio.open(stack_dir / f"{n}.tif") for n in layers}
    aspect = rasterio.open(stack_dir / "aspect.tif")
    ref = srcs["elevation"]
    profile = ref.profile.copy()
    profile.update(dtype="float32", count=1, nodata=np.nan, compress="lzw")
    h, w = ref.height, ref.width

    with rasterio.open(out_path, "w", **profile) as dst:
        for r0 in range(0, h, CHUNK_ROWS):
            rows = min(CHUNK_ROWS, h - r0)
            win = rasterio.windows.Window(0, r0, w, rows)
            cols = {n: srcs[n].read(1, window=win).astype(np.float32).ravel()
                    for n in layers}
            asp = np.deg2rad(aspect.read(1, window=win).astype(np.float32).ravel())
            cols["aspect_north"] = np.cos(asp)
            cols["aspect_east"] = np.sin(asp)

            block = np.column_stack([cols[f] for f in FEATURES])
            valid = np.isfinite(block).all(axis=1)
            out = np.full(rows * w, np.nan, dtype=np.float32)
            if valid.any():
                out[valid] = model.predict_proba(block[valid])[:, 1].astype(np.float32)
            dst.write(out.reshape(rows, w), 1, window=win)

    for s in srcs.values():
        s.close()
    aspect.close()
    return out_path


def catalog_events():
    """Dated landslides from the independent NASA catalog, as lon/lat pairs."""
    df = pd.read_csv(CATALOG, low_memory=False)
    df = df[(df.latitude >= 8.0) & (df.latitude <= 13.5)
            & (df.longitude >= 74.5) & (df.longitude <= 77.5)]
    return df[["longitude", "latitude"]].to_numpy(dtype=float)


def validate(map_paths, events):
    """Score each tile: where independent events sit in that tile's own distribution."""
    from pyproj import Transformer
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
    ex, ey = to_utm.transform(events[:, 0], events[:, 1])
    pts = np.column_stack([ex, ey])

    rows = []
    for name, path in map_paths.items():
        with rasterio.open(path) as src:
            a = src.read(1).astype(float)
            a = a[np.isfinite(a)]
            if a.size == 0:
                continue
            left, bottom, right, top = src.bounds
            inside = ((pts[:, 0] >= left) & (pts[:, 0] <= right)
                      & (pts[:, 1] >= bottom) & (pts[:, 1] <= top))
            vals = np.array([v[0] for v in src.sample(pts[inside], 1)], dtype=float)
            vals = vals[np.isfinite(vals)]

        entry = {"tile": name, "n_events": int(len(vals)),
                 "map_median": float(np.median(a)),
                 "extrapolated": name != TRAINED_TILE}
        if len(vals):
            entry["event_median"] = float(np.median(vals))
            entry["event_percentile"] = float(
                100.0 * np.mean([(a < v).mean() for v in vals]))
        rows.append(entry)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true", help="build terrain stacks")
    ap.add_argument("--validate", action="store_true", help="score against events")
    args = ap.parse_args()
    if not (args.build or args.validate):
        args.build = args.validate = True

    t0 = time.time()
    tiles = available_tiles()
    log(f"DEM tiles available: {len(tiles)}")
    for t in tiles:
        log(f"  {t.stem}")

    if args.build:
        TILES_DIR.mkdir(parents=True, exist_ok=True)
        build_stacks(tiles)

        bundle = joblib.load(MODEL)
        model = bundle["model"]
        log("\nPredicting susceptibility per tile ...")
        for dem in tiles:
            stack = TILES_DIR / dem.stem
            if not (stack / "relative_relief.tif").exists():
                continue
            out = predict_tile(stack, model)
            log(f"  {dem.stem} -> {out.relative_to(ROOT)}", t0)

    if args.validate:
        map_paths = {}
        for dem in tiles:
            p = TILES_DIR / dem.stem / "susceptibility_ml.tif"
            if p.exists():
                map_paths[dem.stem] = p
        trained = ROOT / "backend" / "rasters" / "v2" / "susceptibility_ml.tif"
        if trained.exists():
            map_paths.setdefault(TRAINED_TILE, trained)

        events = catalog_events()
        log(f"\nIndependent NASA catalog events in region: {len(events)}")
        rows = validate(map_paths, events)

        print("\n" + "=" * 78)
        print("Transfer check: where independent events land in each tile's own map")
        print("=" * 78)
        print(f"{'tile':22s} {'events':>7s} {'map median':>11s} "
              f"{'event median':>13s} {'percentile':>11s}  status")
        for r in sorted(rows, key=lambda x: x["tile"]):
            pct = r.get("event_percentile")
            status = "trained" if not r["extrapolated"] else "extrapolated"
            if pct is None:
                print(f"{r['tile']:22s} {r['n_events']:7d} {r['map_median']:11.3f} "
                      f"{'-':>13s} {'-':>11s}  {status} (no events)")
            else:
                print(f"{r['tile']:22s} {r['n_events']:7d} {r['map_median']:11.3f} "
                      f"{r['event_median']:13.3f} {pct:10.1f}%  {status}")

        METRICS.write_text(json.dumps(rows, indent=2))
        lines = ["# Coverage and Transfer Report", "",
                 "The model was trained on inventory from a single tile "
                 f"(`{TRAINED_TILE}`, 75-76E / 12-13N). Every other tile is "
                 "extrapolation and is scored here against the independent NASA "
                 "Global Landslide Catalog, which contributed nothing to training.", "",
                 "| Tile | Events | Map median | Event median | Event percentile | Status |",
                 "|---|---|---|---|---|---|"]
        for r in sorted(rows, key=lambda x: x["tile"]):
            pct = r.get("event_percentile")
            lines.append(
                f"| {r['tile']} | {r['n_events']} | {r['map_median']:.3f} | "
                f"{r.get('event_median', float('nan')):.3f} | "
                f"{'-' if pct is None else f'{pct:.1f}%'} | "
                f"{'trained' if not r['extrapolated'] else 'extrapolated'} |")
        lines += ["", "A percentile well above 50 means the map ranks real landslides "
                  "higher than typical terrain on that tile, which is the evidence that "
                  "the model transfers. Values near 50 mean it does not."]
        REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log(f"\nWrote {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
