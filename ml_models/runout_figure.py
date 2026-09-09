"""
runout_figure.py
Visualise the rebuilt runout: source, transit and deposition over real terrain.

Zooms on the busiest part of the grid, because at full extent a 110 km tile renders
each 30 m corridor sub-pixel and the structure disappears.

Output: docs/figures/runout_comparison.png

Run:  python ml_models/runout_figure.py [--zoom 700]
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
from matplotlib.colors import LightSource, ListedColormap, Normalize
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "backend" / "rasters" / "v2"
OUT = ROOT / "docs" / "figures" / "runout_comparison.png"

ZONE_COLOURS = ["#00000000", "#2563eb", "#f59e0b", "#dc2626"]  # none/depo/transit/source


def load(name, window=None):
    with rasterio.open(V2 / f"{name}.tif") as src:
        a = src.read(1, window=window).astype(float)
        if src.nodata is not None:
            a[a == src.nodata] = np.nan
        return a, src.transform


def busiest_window(size):
    """Find the size x size window containing the most source cells."""
    with rasterio.open(V2 / "hazard_fused.tif") as src:
        zones = src.read(1)
        transform = src.transform
    src_mask = (zones == 3).astype(np.float32)
    # Coarse box filter, then take the peak: cheap way to find the densest area.
    step = max(1, size // 8)
    coarse = ndimage.uniform_filter(src_mask, size=size)[::step, ::step]
    ry, rx = np.unravel_index(np.nanargmax(coarse), coarse.shape)
    cy, cx = ry * step, rx * step
    h, w = zones.shape
    r0 = int(np.clip(cy - size // 2, 0, max(0, h - size)))
    c0 = int(np.clip(cx - size // 2, 0, max(0, w - size)))
    return rasterio.windows.Window(c0, r0, min(size, w - c0), min(size, h - r0)), transform


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zoom", type=int, default=700, help="window size in cells")
    args = ap.parse_args()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    win, full_transform = busiest_window(args.zoom)
    dem, _ = load("elevation", win)
    vel, _ = load("runout_velocity", win)
    with rasterio.open(V2 / "hazard_fused.tif") as src:
        zones = src.read(1, window=win).astype(float)
        win_transform = src.window_transform(win)
    zones[zones == 255] = np.nan

    left, top = win_transform * (0, 0)
    right, bottom = win_transform * (dem.shape[1], dem.shape[0])
    ext = (left, right, bottom, top)

    shade = LightSource(azdeg=315, altdeg=45).hillshade(
        np.nan_to_num(dem, nan=float(np.nanmin(dem))), vert_exag=2.0, dx=30, dy=30)

    fig, axes = plt.subplots(1, 3, figsize=(21, 7.6))
    fig.patch.set_facecolor("white")

    # --- terrain only -------------------------------------------------------
    ax = axes[0]
    ax.imshow(shade, cmap="gray", extent=ext, origin="upper")
    ax.set_title("Terrain\n(Copernicus GLO-30, hillshaded)", fontsize=12, weight="bold")
    ax.set_xticks([]); ax.set_yticks([])

    # --- hazard zones -------------------------------------------------------
    ax = axes[1]
    ax.imshow(shade, cmap="gray", extent=ext, origin="upper", alpha=0.85)
    ax.imshow(zones, cmap=ListedColormap(ZONE_COLOURS), extent=ext, origin="upper",
              vmin=0, vmax=3, alpha=0.75, interpolation="nearest")
    counts = {v: int(np.nansum(zones == v)) for v in (1, 2, 3)}
    ax.set_title(f"Runout zones\nsource {counts[3]:,}   transit {counts[2]:,}   "
                 f"deposition {counts[1]:,}", fontsize=12, weight="bold")
    ax.set_xticks([]); ax.set_yticks([])
    handles = [plt.Line2D([0], [0], marker="s", ls="", markersize=11,
                          markerfacecolor=c, markeredgecolor="none", label=l)
               for c, l in zip(ZONE_COLOURS[1:], ["deposition", "transit", "source"])]
    ax.legend(handles=handles, loc="lower right", fontsize=10, framealpha=0.9)

    # --- velocity + traced corridors ---------------------------------------
    ax = axes[2]
    ax.imshow(shade, cmap="gray", extent=ext, origin="upper", alpha=0.85)
    vmask = np.where(np.isfinite(vel) & (vel > 0), vel, np.nan)
    im = ax.imshow(vmask, cmap="turbo", extent=ext, origin="upper",
                   norm=Normalize(vmin=0, vmax=float(np.nanmax(vmask)) or 1), alpha=0.9)

    paths = json.loads((V2 / "runout_paths.geojson").read_text())
    drawn = 0
    for f in paths["features"]:
        xy = np.asarray(f["geometry"]["coordinates"], dtype=float)
        if xy[:, 0].min() > right or xy[:, 0].max() < left:
            continue
        if xy[:, 1].min() > top or xy[:, 1].max() < bottom:
            continue
        ax.plot(xy[:, 0], xy[:, 1], color="white", lw=1.5, alpha=0.85,
                solid_capstyle="round")
        drawn += 1
    finite_v = vmask[np.isfinite(vmask)]
    ax.set_title(f"Modelled velocity + {drawn} corridors\n"
                 f"median {np.median(finite_v):.1f} m/s, max {finite_v.max():.1f} m/s",
                 fontsize=12, weight="bold")
    ax.set_xlim(left, right); ax.set_ylim(bottom, top)
    ax.set_xticks([]); ax.set_yticks([])
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
    cb.set_label("velocity (m/s)", fontsize=10)

    km = (right - left) / 1000.0
    fig.suptitle(
        f"Rebuilt debris-flow runout - angle of reach + multiple-flow-direction "
        f"spreading  ({km:.0f} km across)",
        fontsize=14, weight="bold", y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(OUT, dpi=115, facecolor="white")
    print(f"Wrote {OUT.relative_to(ROOT)}")
    print(f"  window {dem.shape[0]}x{dem.shape[1]} cells, {km:.1f} km across")
    print(f"  source {counts[3]:,}  transit {counts[2]:,}  deposition {counts[1]:,}")
    print(f"  corridors drawn {drawn}")


if __name__ == "__main__":
    main()
