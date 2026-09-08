"""
conformal.py
Calibrated uncertainty for the susceptibility model.

A probability of 0.8 from a RandomForest is not a promise that 80% of such cells fail.
Tree ensembles are systematically overconfident in the middle of their range, and this
project has already been burned once by numbers that looked authoritative and were not.
Two things are produced here.

**Calibration.** Reliability curves and Expected Calibration Error, measured out-of-fold
under the same spatial blocks used everywhere else, so the reported probability can be
checked against observed frequency.

**Conformal prediction sets.** Split-conformal calibration (Vovk; Angelopoulos & Bates)
converts scores into sets with a distribution-free coverage guarantee: at alpha = 0.1
the set contains the true label at least 90% of the time, whatever the model's own
confidence claims. Cells whose set is {0, 1} are the ones the model genuinely cannot
call - the honest answer is "unknown", and a map that shades those differently is more
trustworthy than one that paints a number everywhere.

This matters most on the nine extrapolated tiles, where the model was never trained and
the baseline comparison showed it failing to beat relative relief.

Outputs:
  ml_models/conformal_report.md
  ml_models/conformal_metrics.json
  backend/rasters/v2/uncertainty.tif   1 where the prediction set is ambiguous

Run:  python ml_models/conformal.py [--alpha 0.1]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold

sys.path.insert(0, str(Path(__file__).parent))
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "real_landslide_dataset.csv"
V2 = ROOT / "backend" / "rasters" / "v2"
REPORT = ROOT / "ml_models" / "conformal_report.md"
METRICS = ROOT / "ml_models" / "conformal_metrics.json"
UNCERTAINTY = V2 / "uncertainty.tif"

from features import DEPLOYED as FEATURES  # canonical set, see features.py
SEED = 42
CHUNK_ROWS = 256


def spatial_groups(df, block_km=5.0):
    size = block_km * 1000.0
    return (np.floor((df.x - df.x.min()) / size).astype(int) * 100000
            + np.floor((df.y - df.y.min()) / size).astype(int))


def out_of_fold(X, y, groups, n_folds=5):
    oof = np.full(len(y), np.nan)
    for tr, te in GroupKFold(n_splits=n_folds).split(X, y, groups):
        m = RandomForestClassifier(
            n_estimators=500, min_samples_leaf=3, max_features="sqrt",
            class_weight="balanced_subsample", random_state=SEED, n_jobs=-1)
        m.fit(X[tr], y[tr])
        oof[te] = m.predict_proba(X[te])[:, 1]
    return oof


def calibration(y, p, bins=10):
    """Reliability curve and Expected Calibration Error."""
    edges = np.linspace(0, 1, bins + 1)
    rows, ece = [], 0.0
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        sel = (p >= lo) & (p < hi if i < bins - 1 else p <= hi)
        if not sel.any():
            continue
        conf = float(p[sel].mean())
        freq = float(y[sel].mean())
        rows.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": int(sel.sum()),
                     "mean_predicted": round(conf, 4),
                     "observed_frequency": round(freq, 4)})
        ece += sel.mean() * abs(conf - freq)
    return rows, float(ece)


def conformal_quantiles(y, p, alpha):
    """Split-conformal thresholds, one per class.

    The non-conformity score is 1 - p(true class). Taking its (1-alpha) quantile within
    each class gives a per-class threshold; a label enters the prediction set when its
    score falls below that class's threshold. Class-conditional calibration matters here
    because landslides are ~10% of the data and a pooled quantile would be dominated by
    the negatives.
    """
    q = {}
    for cls in (0, 1):
        sel = y == cls
        if not sel.any():
            q[cls] = 1.0
            continue
        scores = 1.0 - np.where(cls == 1, p[sel], 1.0 - p[sel])
        n = len(scores)
        level = min(1.0, np.ceil((n + 1) * (1 - alpha)) / n)
        q[cls] = float(np.quantile(scores, level, method="higher"))
    return q


def prediction_sets(p, q):
    """Which labels each cell's prediction set contains."""
    includes_1 = (1.0 - p) <= q[1]
    includes_0 = p <= q[0]
    return includes_0, includes_1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alpha", type=float, default=0.1,
                    help="miscoverage rate; 0.1 targets 90% coverage")
    args = ap.parse_args()

    df = pd.read_csv(DATA).dropna(subset=FEATURES).reset_index(drop=True)
    X = df[FEATURES].to_numpy(dtype=float)
    y = df["landslide"].to_numpy(dtype=int)
    groups = spatial_groups(df)

    print("=" * 66)
    print("Calibration and conformal prediction")
    print("=" * 66)
    print(f"{len(y)} samples, {int(y.sum())} positive, alpha = {args.alpha}\n")

    oof = out_of_fold(X, y, groups)
    ok = np.isfinite(oof)
    y_ok, p_ok = y[ok], oof[ok]

    rows, ece = calibration(y_ok, p_ok)
    print("Reliability (out-of-fold, spatial blocks):")
    print(f"{'bin':>12s} {'n':>6s} {'predicted':>11s} {'observed':>10s}")
    for r in rows:
        print(f"{r['bin']:>12s} {r['n']:6d} {r['mean_predicted']:11.3f} "
              f"{r['observed_frequency']:10.3f}")
    print(f"\nExpected Calibration Error: {ece:.4f}")

    q = conformal_quantiles(y_ok, p_ok, args.alpha)
    inc0, inc1 = prediction_sets(p_ok, q)
    ambiguous = inc0 & inc1
    empty = ~inc0 & ~inc1
    covered = np.where(y_ok == 1, inc1, inc0)

    print(f"\nConformal thresholds: q0 = {q[0]:.4f}, q1 = {q[1]:.4f}")
    print(f"  empirical coverage   {covered.mean():.3f}  (target {1 - args.alpha:.2f})")
    print(f"  ambiguous sets {{0,1}} {ambiguous.mean():.3f}")
    print(f"  empty sets           {empty.mean():.3f}")

    payload = {
        "alpha": args.alpha, "ece": ece, "reliability": rows,
        "q0": q[0], "q1": q[1],
        "empirical_coverage": float(covered.mean()),
        "ambiguous_fraction": float(ambiguous.mean()),
        "empty_fraction": float(empty.mean()),
        "n": int(ok.sum()),
    }

    # Paint ambiguity across the trained tile.
    sus_path = V2 / "susceptibility_ml.tif"
    if sus_path.exists():
        print("\nWriting uncertainty raster ...")
        with rasterio.open(sus_path) as src:
            profile = src.profile.copy()
            profile.update(dtype="float32", count=1, nodata=np.nan, compress="lzw")
            h, w = src.height, src.width
            with rasterio.open(UNCERTAINTY, "w", **profile) as dst:
                amb_cells = 0
                total = 0
                for r0 in range(0, h, CHUNK_ROWS):
                    rows_n = min(CHUNK_ROWS, h - r0)
                    win = rasterio.windows.Window(0, r0, w, rows_n)
                    p = src.read(1, window=win).astype(np.float32)
                    good = np.isfinite(p)
                    a0, a1 = prediction_sets(p, q)
                    amb = (a0 & a1 & good).astype(np.float32)
                    amb[~good] = np.nan
                    dst.write(amb, 1, window=win)
                    amb_cells += int(np.nansum(amb))
                    total += int(good.sum())
        frac = amb_cells / max(total, 1)
        payload["map_ambiguous_fraction"] = frac
        print(f"  {amb_cells:,} of {total:,} cells ambiguous ({100 * frac:.2f}%)")
        print(f"  wrote {UNCERTAINTY.relative_to(ROOT)}")

    METRICS.write_text(json.dumps(payload, indent=2))

    lines = [
        "# Calibration and Conformal Uncertainty", "",
        f"Out-of-fold under spatial blocks, {len(y)} samples, alpha = {args.alpha}.", "",
        f"**Expected Calibration Error: {ece:.4f}**", "",
        "| Probability bin | n | Mean predicted | Observed frequency |",
        "|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['bin']} | {r['n']} | {r['mean_predicted']:.3f} | "
                     f"{r['observed_frequency']:.3f} |")
    lines += ["", "## Conformal prediction sets", "",
              f"- Thresholds: q0 = {q[0]:.4f}, q1 = {q[1]:.4f}",
              f"- Empirical coverage: **{covered.mean():.3f}** "
              f"(guarantee: {1 - args.alpha:.2f})",
              f"- Ambiguous sets, containing both labels: **{ambiguous.mean():.3f}**",
              f"- Empty sets: {empty.mean():.3f}", ""]
    if "map_ambiguous_fraction" in payload:
        lines.append(f"- Ambiguous share of the trained tile: "
                     f"**{100 * payload['map_ambiguous_fraction']:.2f}%** "
                     f"(`backend/rasters/v2/uncertainty.tif`)")
    lines += ["",
              "An ambiguous cell is one the model cannot separate at the requested",
              "confidence. Shading those distinctly is more honest than painting a",
              "single number everywhere, and it matters most on the nine extrapolated",
              "tiles, where the model was never trained and does not beat relative",
              "relief out of sample."]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
