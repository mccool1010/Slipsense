import rasterio
import numpy as np
import sys

print("Starting test.py")
path = "C:/coding/rasters/Flow_Accumulation_clean75.tif"
print("Opening:", path)
with rasterio.open(path) as src:
    fa = src.read(1)

print("Shape:", getattr(fa, 'shape', None))
print("Min:", np.nanmin(fa))
print("Max:", np.nanmax(fa))
# Avoid computing full np.unique on the whole array (can be slow); sample instead
sample = fa.ravel()[::1000]
print("Unique sample (sampled 1/1000):", np.unique(sample)[:20])

if __name__ == '__main__':
    print("test.py done")
