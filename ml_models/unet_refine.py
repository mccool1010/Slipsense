"""
unet_refine.py
Train a U-Net style refiner using susceptibility_ml + slope + DEM as input.
Outputs: susceptibility_dl.tif (refined map)
"""
import sys
print("=== U-Net Refiner Script Started ===", flush=True)

import os
import math
import numpy as np
from glob import glob
from tqdm import tqdm
from scipy.ndimage import zoom

print("Importing rasterio...", flush=True)
import rasterio
from rasterio.windows import Window

print("Importing torch...", flush=True)
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

print("Importing albumentations...", flush=True)
import albumentations as A

print("Importing matplotlib...", flush=True)
import matplotlib.pyplot as plt
print("All imports successful", flush=True)

# -----------------------
# Config
# -----------------------
RASTER_DIR = r"C:\coding\rasters"
OUT_DIR = r"C:\coding\rasters"
SUS_TIF = os.path.join(RASTER_DIR, "susceptibility_ml.tif")
SLOPE_TIF = os.path.join(RASTER_DIR, "slope75.tif")
DEM_TIF = os.path.join(RASTER_DIR, "DEM_filled_75.tif")

PATCH = 256         # patch size (256 recommended)
STRIDE = 128        # overlap for training patches
BATCH = 8
EPOCHS = 5          # reduced for faster training on CPU
LR = 1e-3
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MODEL_OUT = os.path.join(OUT_DIR, "unet_refiner.pth")
OUT_TIF = os.path.join(OUT_DIR, "susceptibility_dl.tif")

print("Device:", DEVICE)

# -----------------------
# Utility: U-Net (lightweight)
# -----------------------
class ConvBlock(nn.Module):
    def __init__(self, in_ch, out_ch):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True)
        )
    def forward(self, x): return self.net(x)

class UNetSmall(nn.Module):
    def __init__(self, in_ch=3, out_ch=1, base=32):
        super().__init__()
        self.enc1 = ConvBlock(in_ch, base)
        self.enc2 = ConvBlock(base, base*2)
        self.enc3 = ConvBlock(base*2, base*4)
        self.pool = nn.MaxPool2d(2)
        self.up = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=False)
        self.dec3 = ConvBlock(base*6, base*2)
        self.dec2 = ConvBlock(base*3, base)
        self.final = nn.Conv2d(base, out_ch, 1)
    def forward(self, x):
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        d3 = self.up(e3)
        d3 = torch.cat([d3, e2], dim=1)
        d3 = self.dec3(d3)
        d2 = self.up(d3)
        d2 = torch.cat([d2, e1], dim=1)
        d2 = self.dec2(d2)
        out = self.final(d2)
        return out

# -----------------------
# Dataset: patch extraction on the fly
# -----------------------
class RasterPatchDataset(Dataset):
    def __init__(self, sus_path, slope_path, dem_path, patch=256, stride=128, transforms=None):
        self.sus_path = sus_path
        self.slope_path = slope_path
        self.dem_path = dem_path
        self.patch = patch
        self.stride = stride
        self.transforms = transforms

        # open to read metadata
        self.sus = rasterio.open(sus_path)
        self.slope = rasterio.open(slope_path)
        self.dem = rasterio.open(dem_path)
        
        # Use susceptibility_ml dimensions as reference
        self.W = self.sus.width
        self.H = self.sus.height
        
        print(f"Reference (susceptibility): {self.H}x{self.W}", flush=True)
        print(f"  Slope: {self.slope.height}x{self.slope.width}", flush=True)
        print(f"  DEM:   {self.dem.height}x{self.dem.width}", flush=True)

        # build list of windows
        self.windows = []
        for y in range(0, self.H - patch + 1, stride):
            for x in range(0, self.W - patch + 1, stride):
                self.windows.append((x, y))

    def __len__(self): return len(self.windows)

    def __getitem__(self, idx):
        x, y = self.windows[idx]
        win = Window(x, y, self.patch, self.patch)
        sus = self.sus.read(1, window=win).astype(np.float32)
        
        # For slope and dem, adjust window if their dimensions differ
        # Read from appropriate location based on their dimensions
        slope_win = Window(x * self.slope.width // self.W, y * self.slope.height // self.H, 
                          self.patch * self.slope.width // self.W, self.patch * self.slope.height // self.H)
        dem_win = Window(x * self.dem.width // self.W, y * self.dem.height // self.H,
                        self.patch * self.dem.width // self.W, self.patch * self.dem.height // self.H)
        
        slope = self.slope.read(1, window=slope_win).astype(np.float32)
        dem = self.dem.read(1, window=dem_win).astype(np.float32)
        
        # Resize slope and dem to match patch size if needed
        if slope.shape != (self.patch, self.patch):
            zoom_factors = (self.patch / slope.shape[0], self.patch / slope.shape[1])
            slope = zoom(slope, zoom_factors, order=1)
        if dem.shape != (self.patch, self.patch):
            zoom_factors = (self.patch / dem.shape[0], self.patch / dem.shape[1])
            dem = zoom(dem, zoom_factors, order=1)

        # normalize each band to 0-1 using simple min-max (per patch)
        def norm(arr):
            a = arr.copy()
            a = np.nan_to_num(a, nan=np.nanmedian(a))
            mn, mx = a.min(), a.max()
            if mx - mn == 0:
                return np.zeros_like(a)
            return (a - mn) / (mx - mn)

        sus_n = norm(sus)
        slope_n = norm(slope)
        dem_n = norm(dem)

        # input channels: sus, slope, dem
        inp = np.stack([sus_n, slope_n, dem_n], axis=0)
        tgt = sus_n[np.newaxis, :, :]  # target is susceptibility normalized

        # augmentation
        if self.transforms:
            aug = self.transforms(image=np.transpose(inp, (1,2,0)), mask=np.transpose(tgt, (1,2,0)))
            inp = np.transpose(aug['image'], (2,0,1)).astype(np.float32)
            tgt = np.transpose(aug['mask'], (2,0,1)).astype(np.float32)

        return torch.from_numpy(inp), torch.from_numpy(tgt)

# -----------------------
# Prepare Dataset + Dataloader
# -----------------------
transforms = A.Compose([
    A.HorizontalFlip(p=0.5),
    A.VerticalFlip(p=0.5),
    A.RandomRotate90(p=0.5),
])

ds = RasterPatchDataset(SUS_TIF, SLOPE_TIF, DEM_TIF, patch=PATCH, stride=STRIDE, transforms=transforms)
print("Total patches:", len(ds), flush=True)
# Note: num_workers=0 on Windows due to rasterio not being pickleable
dl = DataLoader(ds, batch_size=BATCH, shuffle=True, num_workers=0, pin_memory=False)

# -----------------------
# Build model, loss, optimizer
# -----------------------
model = UNetSmall(in_ch=3, out_ch=1, base=32).to(DEVICE)
optimizer = torch.optim.Adam(model.parameters(), lr=LR)
loss_fn = nn.L1Loss()   # L1 for smoother results

# small edge-aware loss helper (optional)
def edge_loss(pred, target):
    # sobel-like gradient (simple)
    kx = torch.tensor([[1,0,-1],[2,0,-2],[1,0,-1]], dtype=torch.float32, device=DEVICE).view(1,1,3,3)
    ky = kx.permute(0,1,3,2)
    gx_p = nn.functional.conv2d(pred, kx, padding=1)
    gy_p = nn.functional.conv2d(pred, ky, padding=1)
    gx_t = nn.functional.conv2d(target, kx, padding=1)
    gy_t = nn.functional.conv2d(target, ky, padding=1)
    return nn.functional.l1_loss(gx_p, gx_t) + nn.functional.l1_loss(gy_p, gy_t)

# -----------------------
# Training loop with Early Stopping
# -----------------------
best_loss = float('inf')
patience = 3  # stop if loss doesn't improve for 3 epochs
patience_counter = 0

try:
    for epoch in range(1, EPOCHS+1):
        model.train()
        running = 0.0
        batch_count = 0
        pbar = tqdm(dl, desc=f"Epoch {epoch}/{EPOCHS}", disable=False)
        for xb, yb in pbar:
            xb = xb.to(DEVICE, dtype=torch.float32)
            yb = yb.to(DEVICE, dtype=torch.float32)
            pred = model(xb)
            loss = loss_fn(pred, yb) + 0.1 * edge_loss(pred, yb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            running += loss.item()
            batch_count += 1
            # Update description with current average loss
            avg_so_far = running / batch_count
            pbar.set_description(f"Epoch {epoch}/{EPOCHS} [loss={avg_so_far:.4f}]")
        
        pbar.close()
        avg_loss = running/len(dl)
        print(f"\n✓ Epoch {epoch}/{EPOCHS} final avg loss: {avg_loss:.5f}", flush=True)
        
        # Early stopping
        if avg_loss < best_loss:
            best_loss = avg_loss
            patience_counter = 0
            print(f"  ✓ Loss improved to {best_loss:.5f}. Saving checkpoint.", flush=True)
            torch.save(model.state_dict(), MODEL_OUT)
        else:
            patience_counter += 1
            print(f"  → Loss did not improve. Patience: {patience_counter}/{patience}", flush=True)
            if patience_counter >= patience:
                print(f"Early stopping triggered at epoch {epoch}. Best loss: {best_loss:.5f}", flush=True)
                break
except Exception as e:
    print(f"ERROR during training: {e}", flush=True)
    import traceback
    traceback.print_exc()

# Save model (final)
torch.save(model.state_dict(), MODEL_OUT)
print("Saved model:", MODEL_OUT, flush=True)

# -----------------------
# Inference: sliding window full image
# -----------------------
print("Starting inference (sliding window compose)...", flush=True)
sus_src = rasterio.open(SUS_TIF)
meta = sus_src.meta.copy()
H = sus_src.height; W = sus_src.width

# prepare output array
out_arr = np.zeros((H, W), dtype=np.float32)
count_arr = np.zeros((H, W), dtype=np.float32)

model.eval()
with torch.no_grad():
    for y in range(0, H - PATCH + 1, STRIDE):
        for x in range(0, W - PATCH + 1, STRIDE):
            win = Window(x, y, PATCH, PATCH)
            sus = sus_src.read(1, window=win).astype(np.float32)
            
            # Read slope and dem with adjusted windows for different dimensions
            with rasterio.open(SLOPE_TIF) as ssrc:
                slope_W, slope_H = ssrc.width, ssrc.height
                slope_win = Window(x * slope_W // W, y * slope_H // H, 
                                  PATCH * slope_W // W, PATCH * slope_H // H)
                slope = ssrc.read(1, window=slope_win).astype(np.float32)
                if slope.shape != (PATCH, PATCH):
                    zoom_factors = (PATCH / slope.shape[0], PATCH / slope.shape[1])
                    slope = zoom(slope, zoom_factors, order=1)
                    
            with rasterio.open(DEM_TIF) as dsrc:
                dem_W, dem_H = dsrc.width, dsrc.height
                dem_win = Window(x * dem_W // W, y * dem_H // H,
                                PATCH * dem_W // W, PATCH * dem_H // H)
                dem = dsrc.read(1, window=dem_win).astype(np.float32)
                if dem.shape != (PATCH, PATCH):
                    zoom_factors = (PATCH / dem.shape[0], PATCH / dem.shape[1])
                    dem = zoom(dem, zoom_factors, order=1)

            # normalize per-patch same as train
            def norm(arr):
                a = np.nan_to_num(arr, nan=np.nanmedian(arr))
                mn, mx = a.min(), a.max()
                if mx - mn == 0:
                    return np.zeros_like(a)
                return (a - mn) / (mx - mn)
            sus_n = norm(sus); slope_n = norm(slope); dem_n = norm(dem)
            inp = np.stack([sus_n, slope_n, dem_n], axis=0)[np.newaxis,...]
            inp_t = torch.from_numpy(inp).to(DEVICE, dtype=torch.float32)
            pred_patch = model(inp_t).cpu().numpy()[0,0,:,:]

            out_arr[y:y+PATCH, x:x+PATCH] += pred_patch
            count_arr[y:y+PATCH, x:x+PATCH] += 1.0

# average overlapping patches
count_arr[count_arr==0] = 1.0
composed = out_arr / count_arr

# Clip to 0-1 and write GeoTIFF
composed = np.clip(composed, 0.0, 1.0)
meta.update(dtype=rasterio.float32, count=1, compress='lzw')

with rasterio.open(OUT_TIF, "w", **meta) as dst:
    dst.write(composed.astype(np.float32), 1)

print("Saved refined susceptibility (DL) to:", OUT_TIF, flush=True)

# optional quick preview (save as PNG instead of show)
try:
    plt.figure(figsize=(12, 10))
    plt.imshow(composed, cmap='magma')
    plt.title('susceptibility_dl (preview)')
    plt.colorbar()
    preview_path = os.path.join(OUT_DIR, "susceptibility_dl_preview.png")
    plt.savefig(preview_path, dpi=100, bbox_inches='tight')
    print(f"Saved preview to: {preview_path}", flush=True)
    plt.close()
except Exception as e:
    print(f"Warning: Could not save preview: {e}", flush=True)
