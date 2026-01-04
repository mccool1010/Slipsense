import sys
import rasterio
import numpy as np
import joblib
import os
from scipy.ndimage import zoom
from rasterio.transform import Affine
from rasterio.crs import CRS

# Debug: write start message
with open(r"C:\coding\Slipsense\ml_models\gen_log.txt", "w") as f:
    f.write("Script execution started\n")

# Force stdout flushing
print("=== Susceptibility Map Generation Started ===", flush=True)

# ---------------------------------------
# 1. Paths
# ---------------------------------------
raster_dir = r"C:\coding\rasters"
model_path = r"C:\coding\Slipsense\ml_models\landslide_model_xgb.pkl"
output_tif = r"C:\coding\rasters\susceptibility_ml.tif"

# ---------------------------------------
# 2. Raster File Mapping (IMPORTANT)
# ---------------------------------------
rasters = {
    "Relative_Relief_75": "Relative_Relief_75.tif",
    "SPI75": "SPI75.tif",
    "TWI_FINAL": "TWI_FINAL.tif",
    "Flow_Accumulation_clean75": "Flow_Accumulation_clean75.tif",
    "aspect75": "aspect75.tif",
    "slope75": "slope75.tif",
    "Elevation": "DEM_filled_75.tif",
    "Distance_to_River_75": "Distance_to_River_75.tif",
    "Drainage_Density_Final": "Drainage_Density_Final.tif"
}

# ---------------------------------------
# 3. Load model
# ---------------------------------------
print("Loading model...")
model = joblib.load(model_path)

# ---------------------------------------
# 4. Read first raster to define geometry
# ---------------------------------------
sample_raster_path = os.path.join(raster_dir, list(rasters.values())[0])
with rasterio.open(sample_raster_path) as src:
    profile = src.profile
    width = src.width
    height = src.height
    transform = src.transform
    crs = src.crs

# ---------------------------------------
# 5. Load all rasters into 3D array
# ---------------------------------------
feature_stack = []

for key, filename in rasters.items():
    path = os.path.join(raster_dir, filename)
    print(f"Reading {path}...", flush=True)
    
    with rasterio.open(path) as src:
        arr = src.read(1).astype("float32")
        
        # Print shape for debugging
        print(f"  Shape: {arr.shape}", flush=True)

        # Replace nodata with mean / 0
        nodata = src.nodata
        if nodata is not None:
            arr[arr == nodata] = np.nan

        arr = np.nan_to_num(arr, nan=np.nanmean(arr))
        
        # Resize to reference shape if different
        if arr.shape != (height, width):
            print(f"  Resizing from {arr.shape} to ({height}, {width})", flush=True)
            zoom_factors = (height / arr.shape[0], width / arr.shape[1])
            arr = zoom(arr, zoom_factors, order=1)  # order=1 for bilinear interpolation

        feature_stack.append(arr)

# Stack into shape (H, W, N_features)
data = np.stack(feature_stack, axis=-1)

print("Raster stack shape:", data.shape)

# ---------------------------------------
# 6. Flatten → Model prediction → Reshape back
# ---------------------------------------
flat = data.reshape(-1, data.shape[-1])
print("Running ML inference...")

pred = model.predict_proba(flat)[:, 1]   # probability of class 1 (landslide)
pred_map = pred.reshape(height, width)

# ---------------------------------------
# 7. Save as GeoTIFF
# ---------------------------------------
print(f"Saving susceptibility map to: {output_tif}")

new_profile = profile.copy()
new_profile.update({
    "dtype": "float32",
    "count": 1,
    "compress": "lzw"
})

with rasterio.open(output_tif, "w", **new_profile) as dst:
    dst.write(pred_map.astype("float32"), 1)

print("DONE! susceptibility_ml.tif generated successfully.")
