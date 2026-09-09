"""
generate_susceptibility_v2.py
Fit the final model on every labelled sample and paint susceptibility across the grid.

Replaces generate_susceptibility_map.py, which fed `DEM_filled_75.tif` to the model as
"Elevation" - a file that actually holds slope in degrees - and `slope75.tif` as slope,
which was computed in EPSG:4326 and pinned at 83-90 degrees everywhere. The deployed
map therefore carried both errors. This version reads the v2 stack, where every layer
is on one EPSG:32643 grid in metric units.

Outputs:
  backend/rasters/v2/susceptibility_ml.tif   probability of landslide per cell
  ml_models/susceptibility_model.pkl         fitted model + feature order + metadata

Run:  python ml_models/generate_susceptibility_v2.py
"""

import json
import time
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import rasterio
from sklearn.ensemble import RandomForestClassifier

sys.path.insert(0, str(Path(__file__).parent))
ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "backend" / "rasters" / "v2"
DATA = ROOT / "data" / "real_landslide_dataset.csv"
MODEL_OUT = ROOT / "ml_models" / "susceptibility_model.pkl"
MAP_OUT = V2 / "susceptibility_ml.tif"
METRICS = ROOT / "ml_models" / "spatial_cv_metrics.json"

from features import DEPLOYED as FEATURES  # canonical set, see features.py

# Raster layer backing each feature; aspect_north/east are derived from aspect.tif.
LAYER_FOR = {f: f for f in FEATURES if not f.startswith("aspect_")}
SEED = 42
CHUNK_ROWS = 256


def log(msg, t0=None):
    print(f"{msg}{f'  [{time.time() - t0:6.1f}s]' if t0 else ''}", flush=True)


def fit_model(df):
    """Fit on all labelled samples using the configuration that won spatial CV."""
    X = df[FEATURES].to_numpy(dtype=float)
    y = df["landslide"].to_numpy(dtype=int)
    model = RandomForestClassifier(
        n_estimators=500, max_depth=None, min_samples_leaf=3,
        max_features="sqrt", class_weight="balanced_subsample",
        random_state=SEED, n_jobs=-1,
    )
    model.fit(X, y)
    return model, X, y


def main():
    t0 = time.time()
    df = pd.read_csv(DATA).dropna(subset=FEATURES)
    log(f"Fitting on {len(df)} samples ({int(df.landslide.sum())} landslide) ...")
    model, X, y = fit_model(df)

    meta = {"features": FEATURES, "n_samples": int(len(df)),
            "n_positive": int(y.sum()), "trained": time.strftime("%Y-%m-%d")}
    if METRICS.exists():
        spatial = json.loads(METRICS.read_text())["spatial"]
        best = max(spatial, key=lambda r: r["pr_auc"])
        meta["spatial_cv"] = best
        log(f"  spatial-CV reference: {best['model']} AUC {best['auc']:.3f} "
            f"PR-AUC {best['pr_auc']:.3f}")
    joblib.dump({"model": model, "meta": meta}, MODEL_OUT)
    log(f"  saved {MODEL_OUT.relative_to(ROOT)}", t0)

    # Open every layer once; predict in row chunks so the full stack never has to be
    # held in memory at float64 (13.4M cells x 12 features would be ~1.3 GB).
    srcs = {name: rasterio.open(V2 / f"{name}.tif") for name in LAYER_FOR}
    aspect_src = rasterio.open(V2 / "aspect.tif")
    ref = srcs["elevation"]
    profile = ref.profile.copy()
    profile.update(dtype="float32", count=1, nodata=np.nan, compress="lzw")
    h, w = ref.height, ref.width
    log(f"Predicting across {h}x{w} grid ...")

    with rasterio.open(MAP_OUT, "w", **profile) as dst:
        for r0 in range(0, h, CHUNK_ROWS):
            rows = min(CHUNK_ROWS, h - r0)
            win = rasterio.windows.Window(0, r0, w, rows)

            cols = {}
            for name in LAYER_FOR:
                cols[name] = srcs[name].read(1, window=win).astype(np.float32).ravel()
            asp = np.deg2rad(aspect_src.read(1, window=win).astype(np.float32).ravel())
            cols["aspect_north"] = np.cos(asp)
            cols["aspect_east"] = np.sin(asp)

            block = np.column_stack([cols[f] for f in FEATURES])
            valid = np.isfinite(block).all(axis=1)

            out = np.full(rows * w, np.nan, dtype=np.float32)
            if valid.any():
                out[valid] = model.predict_proba(block[valid])[:, 1].astype(np.float32)
            dst.write(out.reshape(rows, w), 1, window=win)

            if (r0 // CHUNK_ROWS) % 4 == 0:
                log(f"  rows {r0}-{r0 + rows} of {h}", t0)

    for s in srcs.values():
        s.close()
    aspect_src.close()

    with rasterio.open(MAP_OUT) as chk:
        a = chk.read(1)
        finite = a[np.isfinite(a)]
        log(f"\nWrote {MAP_OUT.relative_to(ROOT)}")
        log(f"  probability  min {finite.min():.3f}  median {np.median(finite):.3f}  "
            f"max {finite.max():.3f}")
        for q in (0.5, 0.7, 0.9):
            log(f"  cells above {q:.1f}: {100 * (finite >= q).mean():5.2f}%")
    log("Done.", t0)


if __name__ == "__main__":
    main()
