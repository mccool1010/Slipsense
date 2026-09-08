"""
sentinel_figure.py
Render before/after Sentinel-2 imagery beside the detected scars and the model's map.

The strongest evidence a susceptibility map can offer is visual: the same hillside
before a monsoon, after it, and what the model said about it beforehand. This renders
that for several Western Ghats areas, not one, so the panel cannot be read as a single
flattering example.

Output: docs/figures/sentinel_change_<area>.png

Run:  python ml_models/sentinel_figure.py [--areas wayanad idukki]
"""

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
import requests
from rasterio.windows import from_bounds

sys.path.insert(0, str(Path(__file__).parent))
from sentinel_inventory import (AREAS, MAX_CLOUD, POST_WINDOW, PRE_WINDOW,  # noqa: E402
                                NDVI_DROP_MIN, POST_NDVI_MAX, STAC)

ROOT = Path(__file__).resolve().parent.parent
SCARS = ROOT / "data" / "sentinel_scars.geojson"
OUTDIR = ROOT / "docs" / "figures"
TILES = ROOT / "backend" / "rasters" / "tiles"
V2 = ROOT / "backend" / "rasters" / "v2"


def search(bbox, window, session):
    body = {"collections": ["sentinel-2-l2a"], "bbox": bbox,
            "datetime": f"{window[0]}/{window[1]}",
            "query": {"eo:cloud_cover": {"lt": MAX_CLOUD}}, "limit": 8}
    r = session.post(STAC, json=body, timeout=120)
    r.raise_for_status()
    return sorted(r.json().get("features", []),
                  key=lambda f: f["properties"].get("eo:cloud_cover", 100))


def read_window(url, bbox):
    with rasterio.open(f"/vsicurl/{url}") as src:
        from pyproj import Transformer
        tr = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        xs, ys = tr.transform([bbox[0], bbox[2]], [bbox[1], bbox[3]])
        win = from_bounds(min(xs), min(ys), max(xs), max(ys), src.transform)
        return (src.read(1, window=win).astype(np.float32),
                src.window_transform(win), src.crs)


def rgb_for(scene, bbox):
    """True-colour composite, contrast-stretched per band for display.

    Two things have to be handled or the panel is unreadable. Sentinel-2 fills outside
    the granule footprint with zeros, which drag the low end of any stretch down and
    leave a hard black wedge; and a single bright cloud pushes the high end up far
    enough to crush everything else to near-black. So zeros are excluded from the
    statistics and masked out, the high cut is taken well below the maximum, and each
    band is stretched independently to keep the colour balance.
    """
    bands = []
    for key in ("red", "green", "blue"):
        arr, transform, crs = read_window(scene["assets"][key]["href"], bbox)
        bands.append(arr)
    h = min(b.shape[0] for b in bands)
    w = min(b.shape[1] for b in bands)
    stack = np.stack([b[:h, :w] for b in bands], axis=-1).astype(np.float32)

    valid = np.all(stack > 0, axis=-1)
    out = np.zeros_like(stack)
    for i in range(3):
        band = stack[..., i]
        sample = band[valid]
        if sample.size == 0:
            continue
        lo, hi = np.percentile(sample, [2, 96])
        out[..., i] = np.clip((band - lo) / max(hi - lo, 1e-6), 0, 1)
    # Mild gamma lifts the shadowed hillsides that dominate this terrain.
    out = np.power(out, 0.85)

    rgba = np.dstack([out, valid.astype(np.float32)])
    return rgba, transform, crs


def ndvi_for(scene, bbox):
    red, transform, crs = read_window(scene["assets"]["red"]["href"], bbox)
    nir, _, _ = read_window(scene["assets"]["nir"]["href"], bbox)
    h, w = min(red.shape[0], nir.shape[0]), min(red.shape[1], nir.shape[1])
    red, nir = red[:h, :w], nir[:h, :w]
    with np.errstate(invalid="ignore", divide="ignore"):
        ndvi = (nir - red) / (nir + red)
    ndvi[~np.isfinite(ndvi)] = np.nan
    return ndvi, transform, crs


def susceptibility_at(bbox):
    """The model's map for this area, if a tile covers it."""
    from pyproj import Transformer
    for path in sorted(TILES.glob("*/susceptibility_ml.tif")) + [
            V2 / "susceptibility_ml.tif"]:
        if not path.exists():
            continue
        with rasterio.open(path) as src:
            tr = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
            xs, ys = tr.transform([bbox[0], bbox[2]], [bbox[1], bbox[3]])
            left, bottom = min(xs), min(ys)
            right, top = max(xs), max(ys)
            b = src.bounds
            if not (left >= b.left and right <= b.right
                    and bottom >= b.bottom and top <= b.top):
                continue
            win = from_bounds(left, bottom, right, top, src.transform)
            arr = src.read(1, window=win).astype(np.float32)
            if arr.size and np.isfinite(arr).any():
                return arr
    return None


def scars_in(area):
    if not SCARS.exists():
        return []
    data = json.loads(SCARS.read_text())
    return [f["geometry"]["coordinates"] for f in data["features"]
            if f["properties"].get("area") == area]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--areas", nargs="*", default=["wayanad", "idukki", "kannur"])
    args = ap.parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": "SlipSense/1.0 (landslide research)"})
    lookup = dict(AREAS)

    for area in args.areas:
        if area not in lookup:
            print(f"unknown area {area}"); continue
        bbox = lookup[area]
        print(f"\n=== {area} {bbox}", flush=True)
        try:
            pre = search(bbox, PRE_WINDOW, session)[0]
            post = search(bbox, POST_WINDOW, session)[0]
        except (requests.RequestException, IndexError) as exc:
            print(f"  no scene pair: {exc}"); continue

        print(f"  pre  {pre['properties']['datetime'][:10]}", flush=True)
        print(f"  post {post['properties']['datetime'][:10]}", flush=True)
        try:
            pre_rgb, _, _ = rgb_for(pre, bbox)
            post_rgb, _, _ = rgb_for(post, bbox)
            pre_ndvi, _, _ = ndvi_for(pre, bbox)
            post_ndvi, _, _ = ndvi_for(post, bbox)
        except Exception as exc:
            print(f"  read failed: {exc}"); continue

        h = min(pre_ndvi.shape[0], post_ndvi.shape[0])
        w = min(pre_ndvi.shape[1], post_ndvi.shape[1])
        drop = pre_ndvi[:h, :w] - post_ndvi[:h, :w]
        scar = (drop >= NDVI_DROP_MIN) & (post_ndvi[:h, :w] <= POST_NDVI_MAX)

        sus = susceptibility_at(bbox)
        ncols = 4 if sus is not None else 3
        fig, axes = plt.subplots(1, ncols, figsize=(5.4 * ncols, 5.8))
        fig.patch.set_facecolor("white")

        for ax in axes:
            ax.set_facecolor("#e2e8f0")
        axes[0].imshow(pre_rgb)
        axes[0].set_title(f"Before — {pre['properties']['datetime'][:10]}",
                          fontsize=12, weight="bold")
        axes[1].imshow(post_rgb)
        axes[1].set_title(f"After — {post['properties']['datetime'][:10]}",
                          fontsize=12, weight="bold")

        axes[2].imshow(post_rgb[:h, :w, :])
        overlay = np.zeros((h, w, 4))
        overlay[scar] = [1.0, 0.1, 0.1, 0.85]
        axes[2].imshow(overlay)
        axes[2].set_title(f"Detected scars — {int(scar.sum()):,} px\n"
                          f"NDVI drop ≥ {NDVI_DROP_MIN}", fontsize=12, weight="bold")

        if sus is not None:
            im = axes[3].imshow(sus, cmap="inferno", vmin=0, vmax=1)
            axes[3].set_title("Model susceptibility\n(predicted independently)",
                              fontsize=12, weight="bold")
            fig.colorbar(im, ax=axes[3], fraction=0.046, pad=0.02)

        for ax in axes:
            ax.set_xticks([]); ax.set_yticks([])

        n_scars = len(scars_in(area))
        fig.suptitle(f"{area.title()} — Sentinel-2 change detection "
                     f"({n_scars} candidate scars mapped)",
                     fontsize=14, weight="bold", y=0.99)
        fig.tight_layout(rect=[0, 0, 1, 0.93])
        out = OUTDIR / f"sentinel_change_{area}.png"
        fig.savefig(out, dpi=110, facecolor="white")
        plt.close(fig)
        print(f"  wrote {out.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
