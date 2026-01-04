import sys
import os

# Write to file for debugging
log_file = r"C:\coding\Slipsense\ml_models\debug.log"

with open(log_file, "w") as f:
    f.write("Script started\n")
    f.flush()

print("Loading rasterio...")
sys.stdout.flush()

import rasterio
import numpy as np
import joblib
from rasterio.transform import Affine
from rasterio.crs import CRS

with open(log_file, "a") as f:
    f.write("Imports successful\n")
    f.flush()

# Paths
raster_dir = r"C:\coding\rasters"
model_path = r"C:\coding\Slipsense\ml_models\landslide_model_xgb.pkl"
output_tif = r"C:\coding\rasters\susceptibility_ml.tif"

with open(log_file, "a") as f:
    f.write(f"Raster dir exists: {os.path.exists(raster_dir)}\n")
    f.write(f"Model exists: {os.path.exists(model_path)}\n")
    f.flush()

print("Loading model...")
sys.stdout.flush()

try:
    model = joblib.load(model_path)
    with open(log_file, "a") as f:
        f.write("Model loaded successfully\n")
        f.flush()
except Exception as e:
    with open(log_file, "a") as f:
        f.write(f"Error loading model: {e}\n")
        f.flush()
    raise

print("Script completed successfully")
sys.stdout.flush()
