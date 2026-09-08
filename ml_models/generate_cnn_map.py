"""
generate_cnn_map.py
Paint the patch CNN across the whole grid to produce the deep-learning susceptibility
layer the backend serves as `susceptibility_dl`.

The CNN is the strongest model under spatial CV (AUC 0.896 vs 0.881 for RandomForest),
because it reads hillslope form around a site rather than only the values beneath it.

Inference is strided rather than per-pixel: the network already integrates a 960 m
context window, so neighbouring pixels produce near-identical outputs and evaluating
every one of the 13.4M cells would be almost entirely redundant work. Predictions are
computed on a coarse lattice and interpolated back up, which is both far faster and
visually smoother.

Output: backend/rasters/v2/susceptibility_dl.tif

Run:  python ml_models/generate_cnn_map.py [--stride 8]
"""

import argparse
import time
from pathlib import Path

import numpy as np
import rasterio
import torch
from scipy.ndimage import zoom

from cnn_context import PatchCNN

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "backend" / "rasters" / "v2"
WEIGHTS = ROOT / "backend" / "rasters" / "cnn_context.pt"
OUT = V2 / "susceptibility_dl.tif"


def log(msg, t0=None):
    print(f"{msg}{f'  [{time.time() - t0:6.1f}s]' if t0 else ''}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=8)
    ap.add_argument("--batch", type=int, default=512)
    args = ap.parse_args()

    t0 = time.time()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    ckpt = torch.load(WEIGHTS, map_location=device, weights_only=False)
    channels, patch, norm = ckpt["channels"], ckpt["patch"], ckpt["norm"]

    model = PatchCNN(len(channels))
    model.load_state_dict(ckpt["state_dict"])
    model.to(device).eval()
    log(f"Loaded CNN: {len(channels)} channels, {patch}x{patch} patches, device {device}")

    bands, profile = [], None
    for spec in norm:
        with rasterio.open(V2 / f"{spec['channel']}.tif") as src:
            a = src.read(1).astype(np.float32)
            if profile is None:
                profile = src.profile.copy()
        finite = np.isfinite(a)
        # Reuse the exact training normalisation; recomputing it here would shift the
        # inputs relative to what the network learned.
        bands.append(np.where(finite, (a - spec["mean"]) / spec["std"], 0.0))
    stack = np.stack(bands)
    valid = np.isfinite(bands[0]) | True
    with rasterio.open(V2 / "elevation.tif") as src:
        nodata = ~np.isfinite(src.read(1))

    c, h, w = stack.shape
    half = patch // 2
    padded = np.pad(stack, ((0, 0), (half, half), (half, half)), constant_values=0.0)
    log(f"Stack {stack.shape}, stride {args.stride}", t0)

    rows = list(range(0, h, args.stride))
    cols = list(range(0, w, args.stride))
    coarse = np.zeros((len(rows), len(cols)), dtype=np.float32)
    log(f"Predicting on a {len(rows)}x{len(cols)} lattice "
        f"({len(rows) * len(cols):,} patches) ...")

    with torch.no_grad():
        for ri, r in enumerate(rows):
            # Build one lattice row of patches at a time; the full set would need
            # several GB held at once.
            row_patches = np.empty((len(cols), c, patch, patch), dtype=np.float32)
            for ci, cc in enumerate(cols):
                row_patches[ci] = padded[:, r:r + patch, cc:cc + patch]

            preds = []
            for s in range(0, len(cols), args.batch):
                xb = torch.from_numpy(row_patches[s:s + args.batch]).to(device)
                preds.append(torch.sigmoid(model(xb)).cpu().numpy())
            coarse[ri] = np.concatenate(preds)

            if ri % 50 == 0:
                log(f"  lattice row {ri}/{len(rows)}", t0)

    log("Interpolating back to full resolution ...", t0)
    full = zoom(coarse, (h / coarse.shape[0], w / coarse.shape[1]), order=1)
    full = np.clip(full[:h, :w], 0.0, 1.0).astype(np.float32)
    full[nodata] = np.nan

    profile.update(dtype="float32", count=1, nodata=np.nan, compress="lzw")
    with rasterio.open(OUT, "w", **profile) as dst:
        dst.write(full, 1)

    finite = full[np.isfinite(full)]
    log(f"\nWrote {OUT.relative_to(ROOT)}")
    log(f"  probability  min {finite.min():.3f}  median {np.median(finite):.3f}  "
        f"max {finite.max():.3f}")
    for q in (0.5, 0.7, 0.9):
        log(f"  cells above {q:.1f}: {100 * (finite >= q).mean():5.2f}%")
    log("Done.", t0)


if __name__ == "__main__":
    main()
