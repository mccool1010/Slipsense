"""
validate_sentinel.py
The decisive test: score the model against satellite-derived scars.

Two explanations survived the earlier analysis for why the model beats relative relief
on its own inventory but not on independent NASA catalog events:

  (a) the catalog is too imprecise to measure a 30 m map against - only 2 of 109 events
      are located "exact", and 15 are ±25-50 km
  (b) the 279 training points are spatially biased in some way, so the model learned how
      they were collected rather than where slopes fail

The road-proximity probe ruled out the most obvious form of (b): landslides sit *farther*
from roads than background, and `dist_road` ranks 10th of 16 by importance.

Sentinel-derived scars separate what remains. They are located to a 10 m pixel rather
than to a district, and they come from a completely different process - satellite change
detection, with no field mapper deciding where to walk. So:

  if the model scores **well** on these but poorly on the catalog, (a) was the problem
      and the model generalises after all
  if it scores **poorly on both**, (b) stands in some form and the ML component is not
      yet justified over relative relief

The same three candidate maps are compared as in `baseline_report.md`, on the same
scale-free percentile metric, so the two tables can be read side by side.

Caveat carried throughout: these scars are **unverified candidates**. NDVI loss on steep
ground is also produced by logging, quarrying, cloud shadow and seasonal agriculture.

Run:  python ml_models/validate_sentinel.py
"""

import json
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
SCARS = ROOT / "data" / "sentinel_scars.geojson"
TILES = ROOT / "backend" / "rasters" / "tiles"
V2 = ROOT / "backend" / "rasters" / "v2"
REPORT = ROOT / "ml_models" / "sentinel_validation_report.md"
METRICS = ROOT / "ml_models" / "sentinel_validation_metrics.json"


def load_scars():
    data = json.loads(SCARS.read_text())
    pts, areas = [], []
    for f in data["features"]:
        lon, lat = f["geometry"]["coordinates"]
        pts.append((lon, lat))
        areas.append(f["properties"].get("area", "?"))
    return np.asarray(pts, dtype=float), areas


def percentiles(paths, lonlat):
    """Mid-rank percentile of each point within each map's own distribution."""
    out, used = [], []
    for path in paths:
        try:
            with rasterio.open(path) as src:
                tr = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                x, y = tr.transform(lonlat[:, 0], lonlat[:, 1])
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
                idx = np.nonzero(inside)[0]
                vals = np.array([v[0] for v in src.sample(pts[inside], 1)], dtype=float)
                for i, v in zip(idx, vals):
                    if not np.isfinite(v):
                        continue
                    below = float((a < v).mean())
                    equal = float((a == v).mean())
                    out.append(100.0 * (below + 0.5 * equal))
                    used.append(int(i))
        except Exception as exc:
            print(f"    ! {Path(path).name}: {exc}")
    return np.asarray(out), used


def main():
    if not SCARS.exists():
        raise SystemExit("Run sentinel_inventory.py first")
    pts, areas = load_scars()
    print("=" * 72)
    print("Validation against Sentinel-2 derived scars")
    print("=" * 72)
    print(f"{len(pts)} candidate scars from "
          f"{len(set(areas))} areas: {sorted(set(areas))}\n")

    candidates = {
        "SlipSense v2 (ML)": sorted(TILES.glob("*/susceptibility_ml.tif")),
        "Slope raster alone": sorted(TILES.glob("*/slope.tif")),
        "Relative relief alone": sorted(TILES.glob("*/relative_relief.tif")),
    }

    rows = []
    for name, paths in candidates.items():
        pct, used = percentiles(paths, pts)
        if pct.size == 0:
            print(f"  {name:24s} no overlap")
            continue
        top20 = float((pct > 80).mean() * 100)
        w = stats.wilcoxon(pct - 50, alternative="greater") if pct.size > 5 else None
        rows.append({
            "map": name, "n": int(pct.size),
            "mean_percentile": float(pct.mean()),
            "median_percentile": float(np.median(pct)),
            "pct_in_top20": top20,
            "enrichment": round(top20 / 20.0, 2),
            "wilcoxon_p": float(w.pvalue) if w else None,
        })
        p = f"{w.pvalue:.2g}" if w else "-"
        print(f"  {name:24s} n={pct.size:3d}  mean {pct.mean():5.1f}%  "
              f"median {np.median(pct):5.1f}%  top-20% {top20:5.1f}%  "
              f"enrich {top20 / 20:.2f}x  p={p}")

    METRICS.write_text(json.dumps({"n_scars": int(len(pts)),
                                   "areas": sorted(set(areas)),
                                   "results": rows}, indent=2))

    ml = next((r for r in rows if r["map"].startswith("SlipSense")), None)
    relief = next((r for r in rows if r["map"].startswith("Relative")), None)

    lines = ["# Validation against Sentinel-2 derived scars", "",
             f"{len(pts)} candidate scars mapped by NDVI change across "
             f"{len(set(areas))} Western Ghats areas, located to a 10 m pixel.", "",
             "| Map | n | Mean percentile | Top-20% share | Enrichment | Wilcoxon p |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        p = f"{r['wilcoxon_p']:.2g}" if r["wilcoxon_p"] is not None else "-"
        lines.append(f"| {r['map']} | {r['n']} | {r['mean_percentile']:.1f}% | "
                     f"{r['pct_in_top20']:.1f}% | {r['enrichment']}x | {p} |")

    lines += ["", "## Comparison with the NASA catalog test", "",
              "From `baseline_report.md`, on 106 catalog events with coordinate errors",
              "up to 50 km:", "",
              "| Map | Mean percentile | Enrichment |", "|---|---|---|",
              "| SlipSense v2 (ML) | 67.6% | 1.89x |",
              "| Slope raster alone | 68.6% | 2.31x |",
              "| Relative relief alone | 70.1% | 2.26x |", ""]

    if ml and relief:
        if ml["mean_percentile"] > relief["mean_percentile"]:
            verdict = (
                f"On well-located scars the ML map reaches the "
                f"**{ml['mean_percentile']:.1f}th percentile** against "
                f"**{relief['mean_percentile']:.1f}** for relative relief - it leads "
                f"where it trailed on the imprecise catalog. That favours explanation "
                f"(a): the catalog's coordinate error was masking real skill, and the "
                f"model does generalise beyond its own inventory.")
        else:
            verdict = (
                f"Even on well-located scars the ML map reaches only the "
                f"**{ml['mean_percentile']:.1f}th percentile** against "
                f"**{relief['mean_percentile']:.1f}** for relative relief. Coordinate "
                f"error was therefore not the explanation, and the ML component still "
                f"does not earn its complexity over a single terrain variable on data "
                f"collected by a different process.")
        lines += ["## Verdict", "", verdict, ""]

    lines += ["> **These scars are unverified candidates.** NDVI loss on steep ground is",
              "> also produced by logging, quarrying, cloud shadow and seasonal",
              "> agriculture. The sample is also small. Treat this as strong evidence,",
              "> not proof."]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
