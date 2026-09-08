"""
baseline_comparison.py
Does the machine learning actually earn its complexity?

A susceptibility model that cannot beat "steep ground is dangerous" has added nothing,
and this comparison was missing from the original project - the retracted results were
only ever compared against other configurations of themselves, never against a trivial
alternative or against published data.

Two independent tests, because they answer different questions.

**Test 1 - predicting the training inventory**, under the same spatial-block CV as the
main model. Establishes whether the extra features carry signal beyond slope.

**Test 2 - ranking 106 independent NASA catalog events**, which contributed nothing to
training. Each candidate map is scored by where those events fall in its own value
distribution, which is scale-free and so lets a probability map, a raw slope raster and
the published GSI susceptibility product be compared on equal terms.

Candidates include the Geological Survey of India's published susceptibility zones - the
external reference this project should be measured against.

Run:  python ml_models/baseline_comparison.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from scipy import stats
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "real_landslide_dataset.csv"
V2 = ROOT / "backend" / "rasters" / "v2"
TILES = ROOT / "backend" / "rasters" / "tiles"
CATALOG = ROOT / "data" / "Global_Landslide_Catalog_Export_rows.csv"
GSI = ROOT / "backend" / "rasters" / "susceptibility_historical_gsi.tif"
REPORT = ROOT / "ml_models" / "baseline_report.md"
METRICS = ROOT / "ml_models" / "baseline_metrics.json"

FULL_FEATURES = [
    "elevation", "slope", "plan_curvature", "profile_curvature",
    "twi", "spi", "flow_acc", "dist_river", "drainage_density",
    "relative_relief", "aspect_north", "aspect_east",
]
SEED = 42
BLOCK_KM = 5.0


def spatial_groups(df, block_km=BLOCK_KM):
    size = block_km * 1000.0
    return (np.floor((df.x - df.x.min()) / size).astype(int) * 100000
            + np.floor((df.y - df.y.min()) / size).astype(int))


def cv_score(X, y, groups, n_folds=5):
    """Out-of-fold AUC and PR-AUC for a RandomForest on the given feature block."""
    oof = np.full(len(y), np.nan)
    for tr, te in GroupKFold(n_splits=n_folds).split(X, y, groups):
        m = RandomForestClassifier(
            n_estimators=400, min_samples_leaf=3, max_features="sqrt",
            class_weight="balanced_subsample", random_state=SEED, n_jobs=-1)
        m.fit(X[tr], y[tr])
        oof[te] = m.predict_proba(X[te])[:, 1]
    ok = np.isfinite(oof)
    return roc_auc_score(y[ok], oof[ok]), average_precision_score(y[ok], oof[ok])


def test_inventory(df):
    """Test 1: can simpler feature sets match the full model on the inventory?"""
    y = df["landslide"].to_numpy(dtype=int)
    groups = spatial_groups(df)
    rng = np.random.default_rng(SEED)

    candidates = {
        "Random scores": None,
        "Slope only": ["slope"],
        "Relative relief only": ["relative_relief"],
        "Slope + relief": ["slope", "relative_relief"],
        "Full model (12 features)": FULL_FEATURES,
    }

    rows = []
    for name, feats in candidates.items():
        if feats is None:
            scores = rng.random(len(y))
            auc = roc_auc_score(y, scores)
            pr = average_precision_score(y, scores)
        else:
            X = df[feats].to_numpy(dtype=float)
            auc, pr = cv_score(X, y, groups)
        rows.append({"model": name, "auc": float(auc), "pr_auc": float(pr),
                     "n_features": 0 if feats is None else len(feats)})
        print(f"  {name:26s} AUC {auc:.3f}   PR-AUC {pr:.3f}")
    return rows


def catalog_points():
    df = pd.read_csv(CATALOG, low_memory=False)
    df = df[(df.latitude >= 8.0) & (df.latitude <= 13.5)
            & (df.longitude >= 74.5) & (df.longitude <= 77.5)]
    return df[["longitude", "latitude"]].to_numpy(dtype=float)


def percentiles_for(paths, events_lonlat, src_crs="EPSG:32643"):
    """Where independent events sit in a candidate map's own distribution."""
    out = []
    for path in paths:
        try:
            with rasterio.open(path) as src:
                tr = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                x, y = tr.transform(events_lonlat[:, 0], events_lonlat[:, 1])
                pts = np.column_stack([x, y])
                left, bottom, right, top = src.bounds
                inside = ((pts[:, 0] >= left) & (pts[:, 0] <= right)
                          & (pts[:, 1] >= bottom) & (pts[:, 1] <= top))
                if not inside.any():
                    continue
                a = src.read(1).astype(float)
                if src.nodata is not None:
                    a[a == src.nodata] = np.nan
                a = a[np.isfinite(a)]
                if a.size == 0:
                    continue
                vals = np.array([v[0] for v in src.sample(pts[inside], 1)], dtype=float)
                vals = vals[np.isfinite(vals)]
                # Mid-rank percentile: strictly-below plus half the ties. Using
                # strictly-below alone is unfair to coarse categorical maps - the GSI
                # product has only three classes, so an event in its "Low" class would
                # score 0 even though half the map shares that class, while a
                # continuous probability map has almost no ties and is unaffected.
                for v in vals:
                    below = float((a < v).mean())
                    equal = float((a == v).mean())
                    out.append(100.0 * (below + 0.5 * equal))
        except Exception as exc:
            print(f"    ! {Path(path).name}: {exc}")
    return np.asarray(out)


def test_independent(events):
    """Test 2: rank independent events with each candidate map."""
    ml_maps = sorted(TILES.glob("*/susceptibility_ml.tif"))
    slope_maps = sorted(TILES.glob("*/slope.tif"))
    relief_maps = sorted(TILES.glob("*/relative_relief.tif"))

    candidates = {
        "SlipSense v2 (ML)": ml_maps,
        "Slope raster alone": slope_maps,
        "Relative relief alone": relief_maps,
    }
    if GSI.exists():
        candidates["GSI published susceptibility"] = [GSI]
    legacy = ROOT / "backend" / "rasters" / "susceptibility_dl.tif"
    if legacy.exists():
        candidates["Pre-v2 deployed map"] = [legacy]

    rows = []
    for name, paths in candidates.items():
        pcts = percentiles_for(paths, events)
        if pcts.size == 0:
            print(f"  {name:30s} no overlap")
            continue
        w = stats.wilcoxon(pcts - 50, alternative="greater") if pcts.size > 10 else None
        top20 = float((pcts > 80).mean() * 100)
        rows.append({
            "map": name, "n_events": int(pcts.size),
            "mean_percentile": float(pcts.mean()),
            "median_percentile": float(np.median(pcts)),
            "pct_in_top20": top20,
            "enrichment_top20": round(top20 / 20.0, 2),
            "wilcoxon_p": float(w.pvalue) if w else None,
        })
        p = f"{w.pvalue:.2g}" if w else "-"
        print(f"  {name:30s} n={pcts.size:3d}  mean {pcts.mean():5.1f}%  "
              f"top-20% {top20:5.1f}%  enrich {top20 / 20:.2f}x  p={p}")
    return rows


def main():
    print("=" * 74)
    print("Baseline comparison")
    print("=" * 74)

    df = pd.read_csv(DATA).dropna(subset=FULL_FEATURES).reset_index(drop=True)
    print(f"\nTest 1 - predicting the training inventory "
          f"({len(df)} samples, spatial-block CV):")
    inventory_rows = test_inventory(df)

    events = catalog_points()
    print(f"\nTest 2 - ranking {len(events)} independent NASA catalog events:")
    independent_rows = test_independent(events)

    METRICS.write_text(json.dumps(
        {"inventory": inventory_rows, "independent": independent_rows}, indent=2))

    best = max(independent_rows, key=lambda r: r["mean_percentile"]) \
        if independent_rows else None

    lines = [
        "# Baseline Comparison", "",
        "Whether the machine learning earns its complexity, tested two ways.",
        "This comparison was absent from the original project: the retracted results",
        "were only compared against other versions of themselves.", "",
        "## Test 1 - predicting the training inventory (spatial-block CV)", "",
        "| Model | Features | AUC | PR-AUC |", "|---|---|---|---|",
    ]
    for r in inventory_rows:
        lines.append(f"| {r['model']} | {r['n_features']} | {r['auc']:.3f} | "
                     f"{r['pr_auc']:.3f} |")

    lines += ["", "## Test 2 - ranking 106 independent NASA catalog events", "",
              "Scale-free: each map is scored by where independent landslides fall in",
              "its own value distribution, so probability maps, a raw slope raster and",
              "the published GSI product can be compared directly. Random would place",
              "events at the 50th percentile and put 20% in the top quintile.", "",
              "| Map | n | Mean percentile | Top-20% share | Enrichment | Wilcoxon p |",
              "|---|---|---|---|---|---|"]
    for r in independent_rows:
        p = f"{r['wilcoxon_p']:.2g}" if r["wilcoxon_p"] is not None else "-"
        lines.append(f"| {r['map']} | {r['n_events']} | {r['mean_percentile']:.1f}% | "
                     f"{r['pct_in_top20']:.1f}% | {r['enrichment_top20']}x | {p} |")
    if best:
        lines += ["", f"Best on independent events: **{best['map']}** "
                      f"({best['mean_percentile']:.1f}th percentile, "
                      f"{best['enrichment_top20']}x top-quintile enrichment)."]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
