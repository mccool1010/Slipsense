"""
segmentation_metrics.py
IoU and Dice for the susceptibility map, against satellite-mapped landslide scars.

These were the first metrics asked of this project, and for a long time they could not
be produced honestly. The original U-Net was an autoencoder trained on its own input, so
it had no segmentation target at all; and the only inventory was 279 *points*, against
which any IoU would have measured agreement with a buffer radius chosen by hand rather
than with a real scar.

The Sentinel-2 change-detection inventory changes that. Those 42 scars are mapped from
NDVI loss at 10 m, so they have genuine extent - a shape, not a coordinate. That makes an
overlap metric meaningful for the first time.

What is measured: thresholding the continuous susceptibility surface at each calibrated
tier turns it into a binary prediction, which is then compared with the scar mask.

    IoU  = |predicted AND actual| / |predicted OR actual|
    Dice = 2|predicted AND actual| / (|predicted| + |actual|)

Two things to keep in view when reading the result.

**Susceptibility is not segmentation.** The map answers "could this slope fail", not
"did this slope fail during 2024". Terrain that is genuinely dangerous but did not fail
in the observation window counts as a false positive here, so IoU is bounded well below
what a true segmentation model would reach. Recall is the more meaningful half.

**The scars are unverified candidates.** NDVI loss on steep ground is also produced by
logging, quarrying and seasonal agriculture.

Run:  python ml_models/segmentation_metrics.py [--buffer 30]
"""

import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import Window

ROOT = Path(__file__).resolve().parent.parent
SCARS = ROOT / "data" / "sentinel_scars.geojson"
TILES = ROOT / "backend" / "rasters" / "tiles"
V2 = ROOT / "backend" / "rasters" / "v2"
REPORT = ROOT / "ml_models" / "segmentation_report.md"
METRICS = ROOT / "ml_models" / "segmentation_metrics.json"

# The calibrated tiers, from ml_models/alert_calibration.json.
TIERS = {"WATCH": 0.374, "HIGH": 0.619, "VERY HIGH": 0.869}


def load_scars():
    data = json.loads(SCARS.read_text())
    out = []
    for f in data["features"]:
        lon, lat = f["geometry"]["coordinates"]
        props = f.get("properties", {})
        # area_m2 is the real mapped extent of the scar; the geometry is only its
        # centroid, so the shape has to be approximated. An equal-area circle is at
        # least the right size, where a fixed radius is neither.
        area_m2 = float(props.get("area_m2") or 0.0)
        out.append((lon, lat, props.get("area"), area_m2))
    return out


def map_for(lon, lat):
    """The susceptibility raster whose footprint contains this point."""
    for path in sorted(TILES.glob("*/susceptibility_ml.tif")) + [
            V2 / "susceptibility_ml.tif"]:
        if not path.exists():
            continue
        with rasterio.open(path) as src:
            tr = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
            x, y = tr.transform(lon, lat)
            left, bottom, right, top = src.bounds
            if left <= x <= right and bottom <= y <= top:
                return path, x, y
    return None, None, None


def confusion_around(path, x, y, radius_m, threshold, context_m):
    """Count TP/FP/FN in a window around one scar.

    The comparison is local rather than map-wide on purpose: measured over an entire
    tile, scars occupy such a tiny fraction that IoU collapses toward zero and reports
    the class imbalance rather than the model. A window a few hundred metres across asks
    the question that matters - within this neighbourhood, does the flagged ground
    coincide with the ground that actually failed?
    """
    with rasterio.open(path) as src:
        res = abs(src.transform.a)
        half = int(round(context_m / res))
        row, col = src.index(x, y)
        r0, c0 = max(0, row - half), max(0, col - half)
        r1 = min(src.height, row + half + 1)
        c1 = min(src.width, col + half + 1)
        if r1 <= r0 or c1 <= c0:
            return None
        win = Window(c0, r0, c1 - c0, r1 - r0)
        block = src.read(1, window=win).astype(float)

        rr, cc = np.mgrid[r0:r1, c0:c1]
        dist = np.hypot((rr - row) * res, (cc - col) * res)
        actual = dist <= radius_m

    valid = np.isfinite(block)
    predicted = valid & (block >= threshold)
    actual = actual & valid

    tp = int((predicted & actual).sum())
    fp = int((predicted & ~actual).sum())
    fn = int((~predicted & actual).sum())
    return tp, fp, fn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-radius", type=float, default=15.0,
                    help="floor on the equal-area radius, half a 30 m cell")
    ap.add_argument("--context", type=float, default=300.0,
                    help="half-width of the evaluation window in metres")
    args = ap.parse_args()

    if not SCARS.exists():
        raise SystemExit("Run sentinel_inventory.py first")
    scars = load_scars()
    print("=" * 72)
    print("Segmentation overlap against Sentinel-2 scars")
    print("=" * 72)
    areas = [a for *_, a in scars if a]
    radii = [float(np.sqrt(a / np.pi)) for a in areas] or [args.min_radius]
    print(f"{len(scars)} candidate scars, equal-area radii "
          f"{min(radii):.0f}-{max(radii):.0f} m (median {np.median(radii):.0f} m), "
          f"{args.context:.0f} m evaluation window\n")

    results = []
    for tier, threshold in TIERS.items():
        tp = fp = fn = 0
        used = 0
        for lon, lat, _area, area_m2 in scars:
            path, x, y = map_for(lon, lat)
            if path is None:
                continue
            radius = max(args.min_radius, float(np.sqrt(area_m2 / np.pi)) if area_m2 else 0.0)
            got = confusion_around(path, x, y, radius, threshold, args.context)
            if got is None:
                continue
            a, b, c = got
            tp += a; fp += b; fn += c
            used += 1

        union = tp + fp + fn
        iou = tp / union if union else 0.0
        dice = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        results.append({"tier": tier, "threshold": threshold, "scars": used,
                        "iou": iou, "dice": dice,
                        "recall": recall, "precision": precision,
                        "tp": tp, "fp": fp, "fn": fn})
        print(f"  {tier:10s} thr {threshold:.3f}  IoU {iou:.3f}  Dice {dice:.3f}  "
              f"recall {recall:.3f}  precision {precision:.3f}   (n={used})")

    METRICS.write_text(json.dumps(
        {"min_radius_m": args.min_radius, "context_m": args.context,
         "n_scars": len(scars), "results": results}, indent=2))

    best = max(results, key=lambda r: r["dice"])
    lines = [
        "# Segmentation Overlap (IoU / Dice)", "",
        f"Susceptibility thresholded at each calibrated tier, compared with "
        f"{len(scars)} Sentinel-2 scars represented as equal-area circles "
        f"(median radius {np.median(radii):.0f} m), evaluated in "
        f"{args.context:.0f} m windows.", "",
        "| Tier | Threshold | IoU | Dice | Recall | Precision | Scars |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r['tier']} | {r['threshold']:.3f} | {r['iou']:.3f} | "
                     f"{r['dice']:.3f} | {r['recall']:.3f} | {r['precision']:.3f} | "
                     f"{r['scars']} |")
    lines += ["",
              f"Best Dice: **{best['dice']:.3f}** at the {best['tier']} tier "
              f"(recall {best['recall']:.3f}).", "",
              "## How to read this", "",
              "These are the metrics originally asked of this project, and they could",
              "not be produced honestly before now: the old U-Net was an autoencoder",
              "with no segmentation target, and a 279-point inventory has no extent to",
              "overlap with. Satellite-mapped scars have real shape, so the question",
              "finally means something.", "",
              "**Susceptibility is not segmentation.** The map answers whether a slope",
              "*could* fail, not whether it *did* during one observation window. Terrain",
              "that is genuinely dangerous but did not fail counts here as a false",
              "positive, which bounds IoU well below what a true segmentation model",
              "would reach. Recall is the more meaningful half of this table.", "",
              "**The scars are unverified candidates** - NDVI loss on steep ground is",
              "also caused by logging, quarrying and seasonal agriculture. Treat this as",
              "indicative, not as a benchmark result."]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
