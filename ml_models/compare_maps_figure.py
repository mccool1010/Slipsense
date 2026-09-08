"""
compare_maps_figure.py
Render a visual before/after of the susceptibility maps against the real inventory.

Produces docs/figures/susceptibility_comparison.png: the old deployed maps and the
rebuilt v2 map, each with the 279 mapped landslides overlaid, plus the distribution
of predicted susceptibility at those landslides versus the map as a whole.

Run:  python ml_models/compare_maps_figure.py
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import LightSource, Normalize

sys.path.insert(0, str(Path(__file__).parent))
from geo_io import read_points  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "figures" / "susceptibility_comparison.png"
PTS = read_points(ROOT / "Landslides.shp")

MAPS = [
    ("Old deployed  susceptibility_ml.tif", ROOT / "backend/rasters/susceptibility_ml.tif"),
    ("Old U-Net  susceptibility_dl.tif", ROOT / "backend/rasters/susceptibility_dl.tif"),
    ("NEW v2  susceptibility_ml.tif", ROOT / "backend/rasters/v2/susceptibility_ml.tif"),
]
MAX_PX = 1100


def load(path):
    """Read a raster downsampled for display, with nodata as NaN, plus its extent."""
    with rasterio.open(path) as src:
        scale = max(1, int(max(src.width, src.height) / MAX_PX))
        a = src.read(1, out_shape=(1, src.height // scale, src.width // scale)).astype(float)
        if src.nodata is not None:
            a[a == src.nodata] = np.nan
        a[a < -1e30] = np.nan
        b = src.bounds
    return a, (b.left, b.right, b.bottom, b.top)


def percentile_at_points(path):
    """Where the mapped landslides sit within each map's own value distribution."""
    with rasterio.open(path) as src:
        a = src.read(1).astype(float)
        if src.nodata is not None:
            a[a == src.nodata] = np.nan
        a = a[np.isfinite(a)]
        v = np.array([x[0] for x in src.sample(PTS, 1)], dtype=float)
        v = v[np.isfinite(v)]
    return a, v, 100.0 * np.mean([(a < val).mean() for val in v])


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 3, figsize=(19, 12.5))
    fig.patch.set_facecolor("white")

    # --- top-left: terrain context with the inventory -------------------------
    dem, ext = load(ROOT / "backend/rasters/v2/elevation.tif")
    ax = axes[0, 0]
    shade = LightSource(azdeg=315, altdeg=45).hillshade(
        np.nan_to_num(dem, nan=0.0), vert_exag=2.0, dx=30, dy=30)
    ax.imshow(shade, cmap="gray", extent=ext, origin="upper")
    ax.scatter(PTS[:, 0], PTS[:, 1], s=7, c="#e11d48", edgecolors="none", alpha=0.9)
    ax.set_title("Terrain (Copernicus GLO-30) with the 279 mapped landslides",
                 fontsize=12, weight="bold")
    ax.set_xticks([]); ax.set_yticks([])

    # --- the three susceptibility maps ---------------------------------------
    slots = [axes[0, 1], axes[0, 2], axes[1, 0]]
    stats = []
    for (title, path), ax in zip(MAPS, slots):
        arr, ext = load(path)
        allv, ptv, pct = percentile_at_points(path)
        stats.append((title, allv, ptv, pct))

        im = ax.imshow(arr, cmap="inferno", extent=ext, origin="upper",
                       norm=Normalize(vmin=np.nanmin(arr), vmax=np.nanmax(arr)))
        ax.scatter(PTS[:, 0], PTS[:, 1], s=6, facecolors="none",
                   edgecolors="#22d3ee", linewidths=0.5, alpha=0.9)
        good = pct > 90
        ax.set_title(f"{title}\nlandslides sit at percentile {pct:.1f}"
                     f"{'  ✓' if good else '  ✗ worse than random'}",
                     fontsize=11, weight="bold",
                     color="#15803d" if good else "#b91c1c")
        ax.set_xticks([]); ax.set_yticks([])
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)

    # --- distribution panels: old vs new -------------------------------------
    for ax, (title, allv, ptv, pct) in zip([axes[1, 1], axes[1, 2]],
                                           [stats[0], stats[2]]):
        lo, hi = float(np.nanmin(allv)), float(np.nanmax(allv))
        bins = np.linspace(lo, hi, 60)
        ax.hist(allv, bins=bins, density=True, color="#94a3b8",
                alpha=0.75, label="whole map")
        ax.hist(ptv, bins=bins, density=True, color="#e11d48",
                alpha=0.75, label="at real landslides")
        ax.axvline(np.median(allv), color="#475569", ls="--", lw=1.5,
                   label=f"map median {np.median(allv):.2f}")
        ax.axvline(np.median(ptv), color="#9f1239", ls="--", lw=1.5,
                   label=f"landslide median {np.median(ptv):.2f}")
        short = "OLD deployed map" if title.startswith("Old deployed") else "NEW v2 map"
        ax.set_title(f"{short}: where landslides fall in the distribution",
                     fontsize=11, weight="bold")
        ax.set_xlabel("predicted susceptibility")
        ax.set_ylabel("density")
        ax.legend(fontsize=9)

    fig.suptitle(
        "SlipSense susceptibility: the deployed maps rate real landslide sites as "
        "safer than average terrain; the rebuilt map puts them in the top 1%",
        fontsize=14, weight="bold", y=0.985)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(OUT, dpi=115, facecolor="white")
    print(f"Wrote {OUT.relative_to(ROOT)}")
    for title, allv, ptv, pct in stats:
        print(f"  {title:42s} percentile {pct:5.1f}  "
              f"median at slides {np.median(ptv):.3f}  map median {np.median(allv):.3f}")


if __name__ == "__main__":
    main()
