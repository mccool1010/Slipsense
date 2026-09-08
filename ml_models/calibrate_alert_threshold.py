"""
calibrate_alert_threshold.py
Recalibrate the alert susceptibility threshold for the rebuilt map.

The 0.75 threshold in backend/alerts.py was tuned against the old map, whose values
sat in a narrow band around a median of 0.57. The rebuilt map is a calibrated
probability: its median is 0.044 and only ~1% of cells exceed 0.7. Carrying 0.75 over
unchanged would silently mute the alert system, because a district average can no
longer approach it.

This script reports the new distribution and picks a threshold by *selectivity* - the
fraction of terrain it flags - rather than by an absolute number that means something
different on each map. It also evaluates how much of the real landslide inventory each
candidate threshold would catch.

Run:  python ml_models/calibrate_alert_threshold.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import rasterio

sys.path.insert(0, str(Path(__file__).parent))
from geo_io import read_points  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# Calibrate against the layer alerts.py reads (RASTERS["susceptibility_ml"], the sharper
# RandomForest map). The CNN map has a different distribution, so the two maps
# do not share thresholds.
NEW_MAP = ROOT / "backend" / "rasters" / "v2" / "susceptibility_ml.tif"
OLD_MAP = ROOT / "backend" / "rasters" / "susceptibility_dl.tif"
OUT = ROOT / "ml_models" / "alert_calibration.json"

# Fraction of terrain each alert tier should flag, chosen so "HIGH" stays rare enough
# to be actionable but common enough to fire during a real monsoon event.
TIERS = {"WATCH": 0.05, "HIGH": 0.01, "VERY HIGH": 0.002}


def stats(path, pts):
    with rasterio.open(path) as src:
        a = src.read(1).astype(float)
        if src.nodata is not None:
            a[a == src.nodata] = np.nan
        a = a[np.isfinite(a)]
        v = np.array([x[0] for x in src.sample(pts, 1)], dtype=float)
        v = v[np.isfinite(v)]
    return a, v


def main():
    pts = read_points(ROOT / "Landslides.shp")
    new_all, new_pts = stats(NEW_MAP, pts)
    old_all, old_pts = stats(OLD_MAP, pts)

    print("=" * 68)
    print("Susceptibility distributions")
    print("=" * 68)
    for label, a, v in (("OLD susceptibility_dl", old_all, old_pts),
                        ("NEW v2 susceptibility_ml", new_all, new_pts)):
        print(f"\n{label}")
        print(f"  whole map   median {np.median(a):.3f}   "
              f"p95 {np.percentile(a, 95):.3f}   p99 {np.percentile(a, 99):.3f}   "
              f"max {a.max():.3f}")
        print(f"  at the 279 real landslides   median {np.median(v):.3f}")
        print(f"  fraction of map above the old 0.75 threshold: "
              f"{100 * (a >= 0.75).mean():.2f}%")

    print("\n" + "=" * 68)
    print("Candidate thresholds for the NEW map, by selectivity")
    print("=" * 68)
    print(f"{'tier':11s} {'flags % of terrain':>19s} {'threshold':>11s} "
          f"{'% of real landslides caught':>29s}")
    chosen = {}
    for tier, frac in TIERS.items():
        thr = float(np.quantile(new_all, 1 - frac))
        caught = 100.0 * (new_pts >= thr).mean()
        chosen[tier] = {"threshold": round(thr, 4),
                        "flags_fraction_of_terrain": frac,
                        "recall_on_inventory": round(caught, 1)}
        print(f"{tier:11s} {100 * frac:18.1f}% {thr:11.3f} {caught:28.1f}%")

    # What the old number would do if carried across unchanged.
    stale = 100.0 * (new_all >= 0.75).mean()
    stale_recall = 100.0 * (new_pts >= 0.75).mean()
    print(f"\nCarrying the old 0.75 across unchanged would flag {stale:.2f}% of terrain "
          f"and catch {stale_recall:.1f}% of the inventory.")
    print("A district *average* over that map cannot reach 0.75, so average-based "
          "alerting would never fire.")

    print("\nRecommended: threshold on the fraction of a district's area above the HIGH "
          "cutoff, not on the district average - an average over mostly-safe terrain is "
          "dominated by the safe majority and hides a genuinely dangerous 2%.")

    OUT.write_text(json.dumps({
        "new_map_median": float(np.median(new_all)),
        "new_map_p99": float(np.percentile(new_all, 99)),
        "old_map_median": float(np.median(old_all)),
        "tiers": chosen,
        "stale_threshold_0_75": {"flags_percent_terrain": round(stale, 3),
                                 "recall_on_inventory": round(stale_recall, 1)},
    }, indent=2))
    print(f"\nWrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
