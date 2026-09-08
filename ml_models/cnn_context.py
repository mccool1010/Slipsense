"""
cnn_context.py
A patch CNN that judges a location from the terrain *around* it, not just beneath it.

This replaces unet_refine.py, which was not a learning model in any meaningful sense:
its target was its own input channel (`tgt = sus_n`, and `sus_n` was also input
channel 0), so it was an autoencoder trained to reproduce the Random Forest output
with an L1 + edge loss. It had no landslide labels, no validation split, and no
segmentation ground truth - which is why no IoU or Dice could ever be reported for it.

Why a patch classifier rather than a U-Net: the inventory is 279 *points*, not mapped
scar polygons. Pixel segmentation needs polygon truth; with point labels an IoU score
would only measure agreement with an arbitrary buffer we drew ourselves. Patch
classification is well posed under point supervision, and it still captures what the
tabular model cannot - hillslope form, convergence, and upslope texture around a site.

Evaluated with the same spatial blocks as train_spatial_cv.py, so the two are directly
comparable and can be ensembled.

Run:  python ml_models/cnn_context.py [--patch 32] [--epochs 30]
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import torch
import torch.nn as nn
from sklearn.metrics import (average_precision_score, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.model_selection import GroupKFold

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "backend" / "rasters" / "v2"
DATA = ROOT / "data" / "real_landslide_dataset.csv"
REPORT = ROOT / "ml_models" / "cnn_report.md"
METRICS = ROOT / "ml_models" / "cnn_metrics.json"
WEIGHTS = ROOT / "backend" / "rasters" / "cnn_context.pt"

CHANNELS = ["elevation", "slope", "plan_curvature", "profile_curvature",
            "twi", "relative_relief"]
SEED = 42


class PatchCNN(nn.Module):
    """Small CNN sized for a few thousand training samples."""

    def __init__(self, in_ch, width=32):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(in_ch, width, 3, padding=1), nn.BatchNorm2d(width), nn.ReLU(),
            nn.Conv2d(width, width, 3, padding=1), nn.BatchNorm2d(width), nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(width, width * 2, 3, padding=1), nn.BatchNorm2d(width * 2), nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(width * 2, width * 4, 3, padding=1), nn.BatchNorm2d(width * 4), nn.ReLU(),
            nn.AdaptiveAvgPool2d(1),
        )
        self.head = nn.Sequential(nn.Flatten(), nn.Dropout(0.3), nn.Linear(width * 4, 1))

    def forward(self, x):
        return self.head(self.features(x)).squeeze(1)


def load_stack():
    """Load the terrain channels into memory with their shared grid transform."""
    arrays, transform, shape = [], None, None
    for name in CHANNELS:
        path = V2 / f"{name}.tif"
        if not path.exists():
            raise SystemExit(f"Missing v2 layer: {path}. Run build_terrain_stack.py first.")
        with rasterio.open(path) as src:
            a = src.read(1).astype(np.float32)
            if transform is None:
                transform, shape = src.transform, a.shape
            elif a.shape != shape:
                raise SystemExit(f"{name} has shape {a.shape}, expected {shape}")
        arrays.append(a)
    return np.stack(arrays), transform


def normalise(stack):
    """Global z-score per channel.

    Deliberately global rather than per-patch: the old script min-max scaled each patch
    independently, which erased absolute magnitude, so a gentle rise and a cliff both
    became a 0-1 ramp. Landslide risk depends on the actual gradient, so scaling must
    be shared across the whole grid.
    """
    out = np.empty_like(stack)
    stats = []
    for i, band in enumerate(stack):
        finite = np.isfinite(band)
        mu = float(band[finite].mean())
        sd = float(band[finite].std()) or 1.0
        out[i] = np.where(finite, (band - mu) / sd, 0.0)
        stats.append({"channel": CHANNELS[i], "mean": mu, "std": sd})
    return out, stats


def extract_patches(stack, transform, xs, ys, size):
    """Cut a size x size window centred on each coordinate, zero-padded at edges."""
    inv = ~transform
    cols, rows = inv * (xs, ys)
    cols = np.round(np.asarray(cols)).astype(int)
    rows = np.round(np.asarray(rows)).astype(int)

    c, h, w = stack.shape
    half = size // 2
    padded = np.pad(stack, ((0, 0), (half, half), (half, half)), constant_values=0.0)

    out = np.zeros((len(xs), c, size, size), dtype=np.float32)
    for i, (r, col) in enumerate(zip(rows, cols)):
        out[i] = padded[:, r:r + size, col:col + size]
    return out


def run_fold(model, Xtr, ytr, Xte, epochs, lr, batch, device):
    """Train one fold and return probabilities for its held-out block."""
    model.to(device)
    pos_weight = torch.tensor([(ytr == 0).sum() / max((ytr == 1).sum(), 1)],
                              dtype=torch.float32, device=device)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)

    Xtr_t = torch.from_numpy(Xtr)
    ytr_t = torch.from_numpy(ytr.astype(np.float32))
    n = len(ytr)
    rng = np.random.default_rng(SEED)

    model.train()
    for _ in range(epochs):
        perm = rng.permutation(n)
        for s in range(0, n, batch):
            idx = perm[s:s + batch]
            xb = Xtr_t[idx].to(device)
            yb = ytr_t[idx].to(device)
            # Terrain has no canonical orientation, so flips and rotations are label
            # preserving and cheaply quadruple the effective sample count.
            if rng.random() < 0.5:
                xb = torch.flip(xb, dims=[3])
            if rng.random() < 0.5:
                xb = torch.flip(xb, dims=[2])
            k = int(rng.integers(0, 4))
            if k:
                xb = torch.rot90(xb, k, dims=[2, 3])

            opt.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            opt.step()
        sched.step()

    model.eval()
    probs = []
    with torch.no_grad():
        Xte_t = torch.from_numpy(Xte)
        for s in range(0, len(Xte), 256):
            xb = Xte_t[s:s + 256].to(device)
            probs.append(torch.sigmoid(model(xb)).cpu().numpy())
    return np.concatenate(probs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patch", type=int, default=32, help="patch size in cells (30 m each)")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--blocks", type=float, default=5.0)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--batch", type=int, default=64)
    args = ap.parse_args()

    torch.manual_seed(SEED)
    np.random.seed(SEED)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    df = pd.read_csv(DATA)
    print(f"Loading {len(CHANNELS)} terrain channels ...", flush=True)
    stack, transform = load_stack()
    stack, stats = normalise(stack)
    print(f"  stack {stack.shape}, device {device}", flush=True)

    print(f"Extracting {args.patch}x{args.patch} patches "
          f"({args.patch * 30} m across) ...", flush=True)
    X = extract_patches(stack, transform, df.x.values, df.y.values, args.patch)
    y = df.landslide.to_numpy(dtype=int)

    size = args.blocks * 1000.0
    groups = (np.floor((df.x - df.x.min()) / size).astype(int) * 100000
              + np.floor((df.y - df.y.min()) / size).astype(int))

    n_folds = min(args.folds, groups.nunique())
    print(f"Spatial CV: {groups.nunique()} blocks at {args.blocks} km, {n_folds} folds\n",
          flush=True)

    oof = np.full(len(y), np.nan)
    for fold, (tr, te) in enumerate(GroupKFold(n_splits=n_folds).split(X, y, groups), 1):
        model = PatchCNN(len(CHANNELS))
        oof[te] = run_fold(model, X[tr], y[tr], X[te], args.epochs, args.lr,
                           args.batch, device)
        print(f"  fold {fold}/{n_folds}: {len(te)} held out, "
              f"AUC {roc_auc_score(y[te], oof[te]):.3f}", flush=True)

    thr = float(np.quantile(oof, 1 - y.mean()))
    pred = (oof >= thr).astype(int)
    metrics = {
        "auc": float(roc_auc_score(y, oof)),
        "pr_auc": float(average_precision_score(y, oof)),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred)),
        "f1": float(f1_score(y, pred)),
        "threshold": thr,
        "patch_cells": args.patch,
        "patch_metres": args.patch * 30,
        "channels": CHANNELS,
        "n_samples": int(len(y)),
        "n_positive": int(y.sum()),
    }

    print("\n" + "=" * 60)
    print(f"Patch CNN, spatial CV")
    print(f"  AUC       {metrics['auc']:.3f}")
    print(f"  PR-AUC    {metrics['pr_auc']:.3f}")
    print(f"  Precision {metrics['precision']:.3f}")
    print(f"  Recall    {metrics['recall']:.3f}")
    print(f"  F1        {metrics['f1']:.3f}")
    print("=" * 60)

    # Refit on everything for the deployable weights.
    print("\nRefitting on all samples for deployment ...", flush=True)
    final = PatchCNN(len(CHANNELS))
    run_fold(final, X, y, X[:1], args.epochs, args.lr, args.batch, device)
    torch.save({"state_dict": final.state_dict(), "channels": CHANNELS,
                "patch": args.patch, "norm": stats}, WEIGHTS)
    print(f"Saved {WEIGHTS.relative_to(ROOT)}")

    METRICS.write_text(json.dumps(metrics, indent=2))
    REPORT.write_text(
        "# Patch CNN Report\n\n"
        f"Terrain-context CNN over {args.patch}x{args.patch} cell patches "
        f"({args.patch * 30} m across), {len(CHANNELS)} channels, spatial-block CV.\n\n"
        "Replaces `unet_refine.py`, which was an autoencoder on its own input and could\n"
        "not produce IoU or Dice. IoU/Dice remain unavailable until the inventory has\n"
        "mapped scar polygons rather than 279 points.\n\n"
        "| Metric | Value |\n|---|---|\n"
        f"| AUC | {metrics['auc']:.3f} |\n"
        f"| PR-AUC | {metrics['pr_auc']:.3f} |\n"
        f"| Precision | {metrics['precision']:.3f} |\n"
        f"| Recall | {metrics['recall']:.3f} |\n"
        f"| F1 | {metrics['f1']:.3f} |\n",
        encoding="utf-8")
    print(f"Wrote {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
