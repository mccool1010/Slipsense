"""
train_spatial_cv.py
Train and evaluate landslide susceptibility models under spatial cross-validation.

Why spatial CV: landslide points cluster along the same slopes and valleys. With a
random split, a test point often sits a few dozen metres from a training point on the
same hillside, sharing nearly identical terrain. The model recalls its neighbour
instead of generalising, and the score is inflated. Splitting by spatial block forces
every evaluation onto ground the model has never seen.

Both schemes are reported side by side so the size of that inflation is visible.

Run:  python ml_models/train_spatial_cv.py [--ratio N] [--blocks KM]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import (average_precision_score, brier_score_loss,
                             confusion_matrix, f1_score, precision_recall_curve,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import GroupKFold, StratifiedKFold

sys.path.insert(0, str(Path(__file__).parent))
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "real_landslide_dataset.csv"
REPORT = ROOT / "ml_models" / "spatial_cv_report.md"
METRICS_JSON = ROOT / "ml_models" / "spatial_cv_metrics.json"

from features import DEPLOYED as FEATURES  # canonical set, see features.py

SEED = 42


def make_models():
    """Models compared. All get balanced class weights; none see spatial coordinates."""
    models = {
        "RandomForest": RandomForestClassifier(
            n_estimators=500, max_depth=None, min_samples_leaf=3,
            max_features="sqrt", class_weight="balanced_subsample",
            random_state=SEED, n_jobs=-1,
        ),
    }
    try:
        from xgboost import XGBClassifier
        models["XGBoost"] = XGBClassifier(
            n_estimators=500, max_depth=5, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, reg_lambda=2.0,
            eval_metric="logloss", random_state=SEED, n_jobs=-1,
        )
    except ImportError:
        pass
    try:
        from lightgbm import LGBMClassifier
        models["LightGBM"] = LGBMClassifier(
            n_estimators=500, max_depth=6, learning_rate=0.05,
            num_leaves=31, subsample=0.8, colsample_bytree=0.8,
            class_weight="balanced", random_state=SEED, n_jobs=-1, verbose=-1,
        )
    except ImportError:
        pass
    return models


def spatial_blocks(df, block_km):
    """Label each sample with the spatial block it falls in (coordinates are metres)."""
    size = block_km * 1000.0
    bx = np.floor((df.x - df.x.min()) / size).astype(int)
    by = np.floor((df.y - df.y.min()) / size).astype(int)
    return bx * 100000 + by


def best_f1_threshold(y, p):
    """Threshold maximising F1, since 0.5 is arbitrary under class imbalance."""
    prec, rec, thr = precision_recall_curve(y, p)
    f1 = np.divide(2 * prec * rec, prec + rec,
                   out=np.zeros_like(prec), where=(prec + rec) > 0)
    if len(thr) == 0:
        return 0.5
    return float(thr[max(0, int(np.argmax(f1)) - 1)])


def evaluate(name, model, X, y, splits):
    """Run cross-validation and collect out-of-fold predictions."""
    oof = np.full(len(y), np.nan)
    for train_idx, test_idx in splits:
        m = model.__class__(**model.get_params())
        m.fit(X[train_idx], y[train_idx])
        oof[test_idx] = m.predict_proba(X[test_idx])[:, 1]

    mask = np.isfinite(oof)
    yv, pv = y[mask], oof[mask]
    thr = best_f1_threshold(yv, pv)
    pred = (pv >= thr).astype(int)

    return {
        "model": name,
        "auc": float(roc_auc_score(yv, pv)),
        "pr_auc": float(average_precision_score(yv, pv)),
        "precision": float(precision_score(yv, pred, zero_division=0)),
        "recall": float(recall_score(yv, pred)),
        "f1": float(f1_score(yv, pred)),
        "brier": float(brier_score_loss(yv, pv)),
        "threshold": thr,
        "confusion": confusion_matrix(yv, pred).tolist(),
        "n": int(mask.sum()),
    }, oof


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ratio", type=int, default=0,
                    help="negatives per positive (0 = use the whole pool)")
    ap.add_argument("--blocks", type=float, default=5.0,
                    help="spatial block size in km")
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args()

    df = pd.read_csv(DATA)
    missing = [f for f in FEATURES if f not in df.columns]
    if missing:
        raise SystemExit(f"Dataset is missing features: {missing}\n"
                         f"Rebuild it with build_real_dataset.py against the v2 stack.")

    if args.ratio > 0:
        rng = np.random.default_rng(SEED)
        pos = df[df.landslide == 1]
        neg = df[df.landslide == 0]
        take = min(len(neg), args.ratio * len(pos))
        neg = neg.iloc[rng.choice(len(neg), take, replace=False)]
        df = pd.concat([pos, neg], ignore_index=True)

    df = df.dropna(subset=FEATURES).reset_index(drop=True)
    X = df[FEATURES].to_numpy(dtype=float)
    y = df["landslide"].to_numpy(dtype=int)
    groups = spatial_blocks(df, args.blocks)

    print("=" * 70)
    print("Spatial cross-validation")
    print("=" * 70)
    print(f"samples {len(y)}  positives {int(y.sum())}  negatives {int((y == 0).sum())}")
    print(f"features {len(FEATURES)}")
    print(f"spatial blocks {groups.nunique()} at {args.blocks} km, {args.folds} folds\n")

    n_folds = min(args.folds, groups.nunique())
    spatial_splits = list(GroupKFold(n_splits=n_folds).split(X, y, groups))
    random_splits = list(StratifiedKFold(args.folds, shuffle=True,
                                         random_state=SEED).split(X, y))

    results = {"spatial": [], "random": []}
    oof_store = {}
    for name, model in make_models().items():
        for scheme, splits in (("spatial", spatial_splits), ("random", random_splits)):
            res, oof = evaluate(name, model, X, y, splits)
            results[scheme].append(res)
            if scheme == "spatial":
                oof_store[name] = oof
            print(f"{name:14s} {scheme:8s} "
                  f"AUC {res['auc']:.3f}  PR-AUC {res['pr_auc']:.3f}  "
                  f"P {res['precision']:.3f}  R {res['recall']:.3f}  "
                  f"F1 {res['f1']:.3f}  Brier {res['brier']:.3f}")

    best = max(results["spatial"], key=lambda r: r["pr_auc"])
    print(f"\nBest under spatial CV: {best['model']} (PR-AUC {best['pr_auc']:.3f})")

    print("\nPermutation importance (spatial holdout, best model):")
    model = make_models()[best["model"]]
    tr, te = spatial_splits[0]
    model.fit(X[tr], y[tr])
    imp = permutation_importance(model, X[te], y[te], n_repeats=10,
                                 random_state=SEED, scoring="average_precision")
    order = np.argsort(imp.importances_mean)[::-1]
    importances = []
    for i in order:
        importances.append({"feature": FEATURES[i],
                            "importance": float(imp.importances_mean[i]),
                            "std": float(imp.importances_std[i])})
        print(f"  {FEATURES[i]:20s} {imp.importances_mean[i]:+.4f} "
              f"+/- {imp.importances_std[i]:.4f}")

    payload = {
        "n_samples": int(len(y)), "n_positive": int(y.sum()),
        "n_negative": int((y == 0).sum()), "features": FEATURES,
        "block_km": args.blocks, "folds": n_folds,
        "spatial": results["spatial"], "random": results["random"],
        "permutation_importance": importances,
    }
    METRICS_JSON.write_text(json.dumps(payload, indent=2))

    lines = [
        "# Spatial Cross-Validation Report", "",
        "All rows are real coordinates sampled against the rebuilt v2 terrain stack.",
        "No synthetic samples. Metrics are out-of-fold.", "",
        f"- Samples: **{len(y)}** ({int(y.sum())} landslide, {int((y == 0).sum())} non-landslide)",
        f"- Spatial blocks: {groups.nunique()} at {args.blocks} km, {n_folds} folds",
        f"- Features: {len(FEATURES)}", "",
        "## Spatial CV (honest estimate)", "",
        "| Model | AUC | PR-AUC | Precision | Recall | F1 | Brier |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results["spatial"]:
        lines.append(f"| {r['model']} | {r['auc']:.3f} | {r['pr_auc']:.3f} | "
                     f"{r['precision']:.3f} | {r['recall']:.3f} | {r['f1']:.3f} | "
                     f"{r['brier']:.3f} |")
    lines += ["", "## Random CV (optimistic - shown for comparison only)", "",
              "| Model | AUC | PR-AUC | Precision | Recall | F1 |", "|---|---|---|---|---|---|"]
    for r in results["random"]:
        lines.append(f"| {r['model']} | {r['auc']:.3f} | {r['pr_auc']:.3f} | "
                     f"{r['precision']:.3f} | {r['recall']:.3f} | {r['f1']:.3f} |")
    lines += ["", "## Permutation importance (best model, spatial holdout)", "",
              "| Feature | Importance | Std |", "|---|---|---|"]
    for it in importances:
        lines.append(f"| {it['feature']} | {it['importance']:+.4f} | {it['std']:.4f} |")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {REPORT.relative_to(ROOT)} and {METRICS_JSON.name}")


if __name__ == "__main__":
    main()
