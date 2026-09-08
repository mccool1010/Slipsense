"""
augmented_model.py
Does adding soil, land cover and road proximity fix the generalisation gap - and is the
inventory biased?

The baseline comparison left one finding outstanding: the 12-feature terrain model beats
relative relief when predicting its own inventory (PR-AUC 0.525 vs 0.313) but not when
ranking 106 independent events (1.89x top-quintile enrichment vs 2.26x). That pattern is
consistent with the model learning the idiosyncrasies of how 279 points were mapped
rather than the physics of where slopes fail.

This script runs the experiment that can distinguish those two explanations.

**If the features were simply incomplete**, adding real soil, vegetation and road data
should lift performance on *both* tests together.

**If the inventory is spatially biased**, distance to road will carry large importance,
and the independent-event score will not improve no matter what is added - because the
extra features describe the terrain better without changing the fact that the labels
record where somebody walked.

Run:  python ml_models/augmented_model.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "real_landslide_dataset.csv"
V2 = ROOT / "backend" / "rasters" / "v2"
CATALOG = ROOT / "data" / "Global_Landslide_Catalog_Export_rows.csv"
REPORT = ROOT / "ml_models" / "augmented_report.md"
METRICS = ROOT / "ml_models" / "augmented_metrics.json"

TERRAIN = [
    "elevation", "slope", "plan_curvature", "profile_curvature",
    "twi", "spi", "flow_acc", "dist_river", "drainage_density",
    "relative_relief", "aspect_north", "aspect_east",
]
SOIL = ["soil_clay", "soil_sand", "soil_index"]
COVER = ["forest_fraction", "bare_fraction"]
ROAD = ["dist_road"]
SEED = 42


def groups_for(df, block_km=5.0):
    size = block_km * 1000.0
    return (np.floor((df.x - df.x.min()) / size).astype(int) * 100000
            + np.floor((df.y - df.y.min()) / size).astype(int))


def cv(df, feats, n_folds=5):
    X = df[feats].to_numpy(dtype=float)
    y = df["landslide"].to_numpy(dtype=int)
    g = groups_for(df)
    oof = np.full(len(y), np.nan)
    for tr, te in GroupKFold(n_splits=n_folds).split(X, y, g):
        m = RandomForestClassifier(
            n_estimators=500, min_samples_leaf=3, max_features="sqrt",
            class_weight="balanced_subsample", random_state=SEED, n_jobs=-1)
        m.fit(X[tr], y[tr])
        oof[te] = m.predict_proba(X[te])[:, 1]
    ok = np.isfinite(oof)
    return (roc_auc_score(y[ok], oof[ok]),
            average_precision_score(y[ok], oof[ok]))


def catalog_events():
    df = pd.read_csv(CATALOG, low_memory=False)
    df = df[(df.latitude >= 8.0) & (df.latitude <= 13.5)
            & (df.longitude >= 74.5) & (df.longitude <= 77.5)]
    return df[["longitude", "latitude"]].to_numpy(dtype=float)


def independent_score(df, feats, events):
    """Fit on everything, predict at independent event locations, and report where
    those predictions sit relative to a large random sample of the same terrain."""
    X = df[feats].to_numpy(dtype=float)
    y = df["landslide"].to_numpy(dtype=int)
    model = RandomForestClassifier(
        n_estimators=500, min_samples_leaf=3, max_features="sqrt",
        class_weight="balanced_subsample", random_state=SEED, n_jobs=-1).fit(X, y)

    srcs = {f: rasterio.open(V2 / f"{f}.tif") for f in feats
            if not f.startswith("aspect_")}
    aspect = rasterio.open(V2 / "aspect.tif")
    ref = srcs[feats[0] if not feats[0].startswith("aspect_") else "slope"]

    tr = Transformer.from_crs("EPSG:4326", ref.crs, always_xy=True)
    ex, ey = tr.transform(events[:, 0], events[:, 1])
    left, bottom, right, top = ref.bounds
    inside = (ex >= left) & (ex <= right) & (ey >= bottom) & (ey <= top)
    pts = np.column_stack([ex[inside], ey[inside]])

    rng = np.random.default_rng(SEED)
    bg = np.column_stack([rng.uniform(left, right, 20000),
                          rng.uniform(bottom, top, 20000)])

    def predict_at(coords):
        cols = {}
        for f, src in srcs.items():
            cols[f] = np.array([v[0] for v in src.sample(coords, 1)], dtype=float)
            if src.nodata is not None:
                cols[f][cols[f] == src.nodata] = np.nan
        asp = np.array([v[0] for v in aspect.sample(coords, 1)], dtype=float)
        rad = np.deg2rad(np.where(asp >= 0, asp, np.nan))
        cols["aspect_north"] = np.nan_to_num(np.cos(rad))
        cols["aspect_east"] = np.nan_to_num(np.sin(rad))
        block = np.column_stack([cols[f] for f in feats])
        good = np.isfinite(block).all(axis=1)
        out = np.full(len(coords), np.nan)
        if good.any():
            out[good] = model.predict_proba(block[good])[:, 1]
        return out[np.isfinite(out)]

    ev = predict_at(pts)
    back = predict_at(bg)
    for s in srcs.values():
        s.close()
    aspect.close()
    if ev.size == 0 or back.size == 0:
        return None
    pct = np.array([100.0 * ((back < v).mean() + 0.5 * (back == v).mean()) for v in ev])
    return {"n_events": int(ev.size), "mean_percentile": float(pct.mean()),
            "pct_in_top20": float((pct > 80).mean() * 100),
            "enrichment": round(float((pct > 80).mean() * 100) / 20.0, 2)}


def main():
    df = pd.read_csv(DATA)
    available = [f for f in TERRAIN + SOIL + COVER + ROAD if f in df.columns]
    missing = [f for f in SOIL + COVER + ROAD if f not in df.columns]
    if missing:
        print(f"Not yet in the dataset (rebuild after their layers exist): {missing}\n")

    sets = {"Terrain only": TERRAIN}
    if all(f in df.columns for f in SOIL):
        sets["Terrain + soil"] = TERRAIN + SOIL
    if all(f in df.columns for f in COVER):
        sets["Terrain + land cover"] = TERRAIN + COVER
    if all(f in df.columns for f in ROAD):
        sets["Terrain + road"] = TERRAIN + ROAD
    sets["Everything available"] = available

    print("=" * 72)
    print("Augmented feature comparison")
    print("=" * 72)
    print(f"{len(df)} samples, {int(df.landslide.sum())} positive\n")

    events = catalog_events()
    rows = []
    for name, feats in sets.items():
        sub = df.dropna(subset=feats)
        auc, pr = cv(sub, feats)
        ind = independent_score(sub, feats, events)
        rows.append({"features": name, "n_features": len(feats),
                     "auc": auc, "pr_auc": pr, "independent": ind})
        line = f"  {name:24s} ({len(feats):2d} feats)  AUC {auc:.3f}  PR-AUC {pr:.3f}"
        if ind:
            line += (f"   |  independent: {ind['mean_percentile']:.1f}th pct, "
                     f"{ind['enrichment']}x")
        print(line, flush=True)

    # The bias probe: how much does the model lean on distance to road?
    importance_rows = []
    if "dist_road" in df.columns:
        feats = available
        sub = df.dropna(subset=feats)
        X = sub[feats].to_numpy(dtype=float)
        y = sub["landslide"].to_numpy(dtype=int)
        g = groups_for(sub)
        tr, te = next(iter(GroupKFold(n_splits=5).split(X, y, g)))
        m = RandomForestClassifier(
            n_estimators=500, min_samples_leaf=3, max_features="sqrt",
            class_weight="balanced_subsample", random_state=SEED, n_jobs=-1)
        m.fit(X[tr], y[tr])
        imp = permutation_importance(m, X[te], y[te], n_repeats=10,
                                     random_state=SEED, scoring="average_precision")
        order = np.argsort(imp.importances_mean)[::-1]
        print("\nPermutation importance (spatial holdout):")
        for i in order:
            importance_rows.append({"feature": feats[i],
                                    "importance": float(imp.importances_mean[i])})
            marker = "  <-- bias probe" if feats[i] == "dist_road" else ""
            print(f"  {feats[i]:20s} {imp.importances_mean[i]:+.4f}{marker}")

        rank = [r["feature"] for r in importance_rows].index("dist_road") + 1
        print(f"\ndist_road ranks {rank} of {len(feats)} by permutation importance.")

    METRICS.write_text(json.dumps(
        {"sets": rows, "importance": importance_rows}, indent=2))

    lines = ["# Augmented Feature Comparison", "",
             "Whether adding soil, land cover and road proximity closes the gap between",
             "predicting the training inventory and ranking independent events.", "",
             "| Feature set | n | AUC | PR-AUC | Independent mean pct | Enrichment |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        ind = r["independent"]
        lines.append(
            f"| {r['features']} | {r['n_features']} | {r['auc']:.3f} | "
            f"{r['pr_auc']:.3f} | "
            f"{ind['mean_percentile']:.1f}% | {ind['enrichment']}x |"
            if ind else
            f"| {r['features']} | {r['n_features']} | {r['auc']:.3f} | "
            f"{r['pr_auc']:.3f} | - | - |")
    if importance_rows:
        lines += ["", "## Permutation importance", "",
                  "| Feature | Importance |", "|---|---|"]
        for r in importance_rows:
            note = " **(bias probe)**" if r["feature"] == "dist_road" else ""
            lines.append(f"| {r['feature']}{note} | {r['importance']:+.4f} |")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
