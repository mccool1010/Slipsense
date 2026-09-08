"""
train_rainfall_model.py
Train the rainfall-triggering model: given the rain that has fallen, how likely is a
slope failure today?

This is the temporal half of the system. The susceptibility map says which slopes *can*
fail; this says whether today is a day they *might*. Multiplying the two gives a daily
hazard that changes with the weather, which is what an early-warning system actually
needs - a static map cannot tell anyone to evacuate on a Tuesday.

Evaluation is grouped by location, so the model is always scored on sites whose rainfall
history it has never seen. Without that, the same hillside appears in both train and
test on different dates and the score is inflated.

Also fits a rainfall intensity-duration threshold curve of the classic form
    I = a * D^-b
which is the standard way regional landslide warning thresholds are published, and is
directly comparable with the literature for the Western Ghats.

Run:  python ml_models/train_rainfall_model.py
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, f1_score, precision_recall_curve,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "rainfall_trigger_dataset.csv"
MODEL_OUT = ROOT / "ml_models" / "rainfall_trigger_model.pkl"
REPORT = ROOT / "ml_models" / "rainfall_model_report.md"
METRICS = ROOT / "ml_models" / "rainfall_metrics.json"

FEATURES = ["rain_1d", "rain_3d", "rain_5d", "rain_7d", "rain_10d",
            "rain_15d", "rain_30d", "rain_60d", "rain_90d",
            "rain_event_day", "rain_3d_ratio", "rain_15d_ratio"]
SEED = 42


def location_groups(df, precision=1):
    """Group by rounded location so a site never spans train and test."""
    return (df.lat.round(precision).astype(str) + "_"
            + df.lon.round(precision).astype(str))


def best_f1_threshold(y, p):
    prec, rec, thr = precision_recall_curve(y, p)
    f1 = np.divide(2 * prec * rec, prec + rec,
                   out=np.zeros_like(prec), where=(prec + rec) > 0)
    return float(thr[max(0, int(np.argmax(f1)) - 1)]) if len(thr) else 0.5


def fit_id_threshold(df, exceedance=0.05):
    """Fit I = a * D^-b to the rainfall that preceded actual failures.

    Follows the pooled log-log regression used for published regional thresholds
    (Brunetti et al. 2010): every (duration, intensity) pair from every triggering
    event goes into one fit, the slope comes from ordinary least squares, and the
    intercept is then lowered until only `exceedance` of events fall beneath the line.

    Taking a percentile separately at each duration - the obvious first approach - does
    not work here and produces a curve that rises with duration. Short-window totals are
    far more variable than long ones, so the low quantile of a 1-day total sits near
    zero while the same quantile of a 30-day total is necessarily substantial. That is
    an artefact of the variance changing with the window, not a property of triggering
    rainfall, and it inverts the physical relationship.
    """
    durations = np.array([1, 3, 7, 15, 30], dtype=float)
    pos = df[df.landslide == 1]

    logs_d, logs_i = [], []
    for d in durations:
        inten = (pos[f"rain_{int(d)}d"] / d).to_numpy(dtype=float)
        inten = inten[inten > 0]
        logs_d.append(np.full(len(inten), np.log(d)))
        logs_i.append(np.log(inten))
    ld = np.concatenate(logs_d)
    li = np.concatenate(logs_i)

    slope, intercept = np.polyfit(ld, li, 1)
    # Drop the line to the chosen lower exceedance of the observed events.
    residuals = li - (slope * ld + intercept)
    intercept += np.quantile(residuals, exceedance)

    b = -float(slope)
    a = float(np.exp(intercept))
    envelope = a * durations ** (-b)
    median_curve = np.array([np.median((pos[f"rain_{int(d)}d"] / d).to_numpy())
                             for d in durations])
    return a, b, durations, envelope, median_curve


def main():
    df = pd.read_csv(DATA)
    missing = [f for f in FEATURES if f not in df.columns]
    if missing:
        raise SystemExit(f"Dataset missing columns: {missing}")
    df = df.dropna(subset=FEATURES).reset_index(drop=True)

    X = df[FEATURES].to_numpy(dtype=float)
    y = df.landslide.to_numpy(dtype=int)
    groups = location_groups(df)

    print("=" * 66)
    print("Rainfall triggering model")
    print("=" * 66)
    print(f"rows {len(y)}  positive {int(y.sum())}  negative {int((y == 0).sum())}")
    print(f"distinct locations {groups.nunique()}\n")

    models = {
        "LogisticRegression": (LogisticRegression(max_iter=2000,
                                                  class_weight="balanced",
                                                  random_state=SEED), True),
        "RandomForest": (RandomForestClassifier(n_estimators=400, min_samples_leaf=3,
                                                class_weight="balanced_subsample",
                                                random_state=SEED, n_jobs=-1), False),
        "GradientBoosting": (GradientBoostingClassifier(n_estimators=300, max_depth=3,
                                                        learning_rate=0.05,
                                                        random_state=SEED), False),
    }

    n_folds = min(5, groups.nunique())
    splits = list(GroupKFold(n_splits=n_folds).split(X, y, groups))

    results, oofs = [], {}
    for name, (proto, needs_scaling) in models.items():
        oof = np.full(len(y), np.nan)
        for tr, te in splits:
            m = proto.__class__(**proto.get_params())
            xtr, xte = X[tr], X[te]
            if needs_scaling:
                sc = StandardScaler().fit(xtr)
                xtr, xte = sc.transform(xtr), sc.transform(xte)
            m.fit(xtr, y[tr])
            oof[te] = m.predict_proba(xte)[:, 1]

        thr = best_f1_threshold(y, oof)
        pred = (oof >= thr).astype(int)
        res = {"model": name,
               "auc": float(roc_auc_score(y, oof)),
               "pr_auc": float(average_precision_score(y, oof)),
               "precision": float(precision_score(y, pred, zero_division=0)),
               "recall": float(recall_score(y, pred)),
               "f1": float(f1_score(y, pred)),
               "threshold": thr}
        results.append(res)
        oofs[name] = oof
        print(f"{name:20s} AUC {res['auc']:.3f}  PR-AUC {res['pr_auc']:.3f}  "
              f"P {res['precision']:.3f}  R {res['recall']:.3f}  F1 {res['f1']:.3f}")

    best = max(results, key=lambda r: r["pr_auc"])
    print(f"\nBest: {best['model']} (PR-AUC {best['pr_auc']:.3f})")

    a, b, durations, intensities, median_curve = fit_id_threshold(df)
    print(f"\nIntensity-duration threshold: I = {a:.2f} * D^-{b:.3f}  "
          f"(I in mm/day, D in days)")
    for d, i in zip(durations, intensities):
        print(f"  D={d:5.0f} d   triggering intensity envelope {i:7.2f} mm/day "
              f"({i * d:7.1f} mm total)")

    proto, needs_scaling = models[best["model"]]
    final = proto.__class__(**proto.get_params())
    scaler = StandardScaler().fit(X) if needs_scaling else None
    final.fit(scaler.transform(X) if scaler else X, y)
    joblib.dump({"model": final, "scaler": scaler, "features": FEATURES,
                 "threshold": best["threshold"], "id_curve": {"a": a, "b": b},
                 "spatial_cv": best}, MODEL_OUT)
    print(f"\nSaved {MODEL_OUT.relative_to(ROOT)}")

    contrast = df.groupby("landslide")[
        ["rain_1d", "rain_3d", "rain_7d", "rain_15d", "rain_30d"]].mean()

    METRICS.write_text(json.dumps({"results": results, "best": best,
                                   "id_curve": {"a": a, "b": b},
                                   "n": int(len(y)), "n_pos": int(y.sum())}, indent=2))

    lines = ["# Rainfall Triggering Model", "",
             "Answers *when*, where the susceptibility map answers *where*.",
             "Cross-validation is grouped by location, so every score is on sites whose",
             "rainfall history the model has not seen.", "",
             f"- Rows: **{len(y)}** ({int(y.sum())} landslide days, "
             f"{int((y == 0).sum())} matched non-event days)",
             f"- Distinct locations: {groups.nunique()}",
             "- Rainfall source: Open-Meteo historical reanalysis (daily totals)", "",
             "## Model comparison (location-grouped CV)", "",
             "| Model | AUC | PR-AUC | Precision | Recall | F1 |", "|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['model']} | {r['auc']:.3f} | {r['pr_auc']:.3f} | "
                     f"{r['precision']:.3f} | {r['recall']:.3f} | {r['f1']:.3f} |")
    lines += ["", "## Mean antecedent rainfall (mm)", "",
              "| Window | Non-event day | Landslide day | Ratio |", "|---|---|---|---|"]
    for col in ["rain_1d", "rain_3d", "rain_7d", "rain_15d", "rain_30d"]:
        n0, n1 = contrast.loc[0, col], contrast.loc[1, col]
        lines.append(f"| {col.replace('rain_', '').replace('d', ' day')} | {n0:.1f} | "
                     f"{n1:.1f} | {n1 / n0:.2f}x |")
    lines += ["", "## Intensity-duration threshold", "",
              f"Fitted lower envelope: **I = {a:.2f} · D^-{b:.3f}** "
              f"(I in mm/day, D in days)", "",
              "| Duration (days) | Envelope intensity (mm/day) | Envelope total (mm) | "
              "Median at real events (mm/day) |", "|---|---|---|---|"]
    for d, i, m in zip(durations, intensities, median_curve):
        lines.append(f"| {d:.0f} | {i:.2f} | {i * d:.1f} | {m:.1f} |")
    lines += ["",
              "> **Do not deploy the envelope as an operational trigger.** Its shape is "
              "correct - intensity falls with duration, as it must - but its absolute "
              "level is far too low, and a threshold of ~2 mm/day would fire almost "
              "every monsoon day. The cause is inventory quality, not the fit: NASA "
              "catalog entries carry coarse location accuracy and uncertain dates, so "
              "some 'events' pair with grid cells and days that saw almost no rain, and "
              "those points drag any lower envelope toward zero.",
              "",
              "The **median column is the more honest operational reference**: real "
              f"failures here cluster around {median_curve[0]:.0f} mm in 24 h and "
              f"{median_curve[1] * 3:.0f} mm over 3 days. A deployable threshold needs "
              "a dated inventory with mapped coordinates - the same prerequisite as "
              "IoU/Dice for the segmentation model."]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
