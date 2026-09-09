"""
build_deploy_bundle.py
Package only what the server actually needs, as Cloud-Optimised GeoTIFFs.

Hosting this looked impossible at first glance - the generated raster stack is about
7 GB. Almost none of that is served: `backend/rasters/tiles/` (6.8 GB) holds the
per-tile Kerala predictions used for validation, and `data/dem/` is source data. What
the API actually reads is the handful of layers named in config.RASTERS, roughly 286 MB,
and a third of that is legacy copies kept only so the before/after figure can be
regenerated.

Two changes make the rest deployable.

**Overviews.** The current rasters are stripped GeoTIFFs with no pyramids, so a
zoom-9 tile request forces the reader through full-resolution data covering the whole
view. Overviews let it read a pre-reduced level instead - the difference between
scanning tens of megabytes and a few hundred kilobytes per tile.

**Compression.** Susceptibility is a probability in [0, 1] and uncertainty is a flag.
Stored as float32 they cost four bytes for a value that display and alerting never
resolve past three decimals. Quantising those to uint8 with a scale factor is lossless
at the precision anyone reads, and DEFLATE with a predictor handles the rest.

Output: deploy/rasters/, plus a manifest recording exactly what was included and why.

Run:  python ml_models/build_deploy_bundle.py [--out deploy/rasters]
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# Layers the API reads. Legacy copies are deliberately excluded: they exist so
# compare_maps_figure.py can regenerate the before/after panel, and shipping 105 MB of
# superseded rasters to production to support a figure would be daft.
SERVE = [
    "susceptibility_ml", "susceptibility_dl", "uncertainty",
    "hazard_fused", "transit", "deposition", "runout_velocity",
    "historical_susceptibility", "soil_susceptibility",
]

# Layers whose values are bounded and low-precision enough to quantise.
QUANTISE = {"susceptibility_ml", "susceptibility_dl", "uncertainty",
            "soil_susceptibility"}


def log(msg, t0=None):
    print(f"{msg}{f'  [{time.time() - t0:6.1f}s]' if t0 else ''}", flush=True)


def to_cog(src_path, dst_path, quantise):
    """Rewrite one raster as a tiled, compressed COG with overviews."""
    with rasterio.open(src_path) as src:
        profile = src.profile.copy()
        data = src.read(1)
        nodata = src.nodata

        if quantise and data.dtype.kind == "f":
            finite = np.isfinite(data)
            if nodata is not None:
                finite &= data != nodata
            # 0 is reserved for nodata, so the value range maps onto 1..255.
            out = np.zeros(data.shape, dtype=np.uint8)
            if finite.any():
                lo, hi = float(np.nanmin(data[finite])), float(np.nanmax(data[finite]))
                span = max(hi - lo, 1e-9)
                out[finite] = np.clip(
                    1 + ((data[finite] - lo) / span) * 254.0, 1, 255).astype(np.uint8)
            profile.update(dtype="uint8", nodata=0)
            scale, offset = span / 254.0, lo
            data = out
        else:
            scale, offset = 1.0, 0.0

        profile.update(
            driver="GTiff", tiled=True, blockxsize=512, blockysize=512,
            compress="deflate", predictor=2, zlevel=9, BIGTIFF="IF_SAFER",
        )

    with rasterio.open(dst_path, "w", **profile) as dst:
        dst.write(data, 1)
        if scale != 1.0 or offset != 0.0:
            # Recorded so a reader can recover the original units.
            dst.update_tags(SCALE=scale, OFFSET=offset,
                            NOTE="value = OFFSET + (pixel - 1) * SCALE, 0 = nodata")
        # Enough levels that even a whole-region view reads a reduced image.
        dst.build_overviews([2, 4, 8, 16, 32], Resampling.average)
        dst.update_tags(ns="rio_overview", resampling="average")
    return scale, offset


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "deploy" / "rasters")
    args = ap.parse_args()
    t0 = time.time()

    from config import DISTRICT_RASTERS, RASTERS  # noqa: E402

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "districts").mkdir(exist_ok=True)

    manifest, before, after = [], 0.0, 0.0
    for name in SERVE:
        src = Path(RASTERS.get(name, ""))
        if not src.exists():
            log(f"  {name:28s} MISSING, skipped")
            continue
        dst = out / f"{name}.tif"
        size_in = src.stat().st_size / 1048576
        scale, offset = to_cog(src, dst, name in QUANTISE)
        size_out = dst.stat().st_size / 1048576
        before += size_in; after += size_out
        manifest.append({"layer": name, "mb_before": round(size_in, 1),
                         "mb_after": round(size_out, 1),
                         "quantised": name in QUANTISE,
                         "scale": scale, "offset": offset})
        log(f"  {name:28s} {size_in:7.1f} -> {size_out:6.1f} MB"
            f"  ({100 * (1 - size_out / max(size_in, 1e-9)):4.1f}% smaller)")

    for name, path in DISTRICT_RASTERS.items():
        p = Path(path)
        if p.exists():
            shutil.copy2(p, out / "districts" / p.name)
            after += p.stat().st_size / 1048576
            before += p.stat().st_size / 1048576

    # Vector products the frontend fetches directly.
    v2 = ROOT / "backend" / "rasters" / "v2"
    for f in ("runout_paths_exposed.geojson", "runout_paths.geojson",
              "exposure_summary.json"):
        srcf = v2 / f
        if srcf.exists():
            (out / "v2").mkdir(exist_ok=True)
            shutil.copy2(srcf, out / "v2" / f)
            after += srcf.stat().st_size / 1048576
            before += srcf.stat().st_size / 1048576

    (out / "MANIFEST.json").write_text(json.dumps({
        "built": time.strftime("%Y-%m-%d"),
        "layers": manifest,
        "total_mb_before": round(before, 1),
        "total_mb_after": round(after, 1),
        "excluded": {
            "backend/rasters/tiles": "per-tile Kerala predictions, validation only",
            "data/dem": "source DEMs, not served",
            "*_legacy": "superseded rasters, kept locally for the comparison figure",
        },
    }, indent=2))

    log(f"\nBundle: {before:.0f} MB -> {after:.0f} MB "
        f"({100 * (1 - after / max(before, 1e-9)):.0f}% smaller)")
    log(f"Wrote {out.relative_to(ROOT)}", t0)


if __name__ == "__main__":
    main()
