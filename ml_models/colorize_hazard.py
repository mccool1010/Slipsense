import rasterio
import numpy as np
from PIL import Image

in_tif = 'C:/coding/rasters/hazard_fused.tif'
out_png = 'C:/coding/rasters/hazard_fused_color.png'
out_tif = 'C:/coding/rasters/hazard_fused_colormap.tif'

# Define colors: 0=black, 1=blue (if present), 2=yellow, 3=red
colormap = {
    0: (0, 0, 0),
    1: (0, 0, 255),
    2: (255, 200, 0),
    3: (255, 0, 0)
}

with rasterio.open(in_tif) as src:
    arr = src.read(1).astype('uint8')
    profile = src.profile.copy()

# Create RGB image by mapping values
h, w = arr.shape
rgb = np.zeros((h, w, 3), dtype='uint8')
for val, color in colormap.items():
    mask = (arr == val)
    if mask.any():
        rgb[mask] = color

# Save PNG
Image.fromarray(rgb).save(out_png)
print('Saved color PNG:', out_png)

# Save GeoTIFF with embedded colormap
profile.update(count=1, dtype='uint8', compress='lzw')
with rasterio.open(out_tif, 'w', **profile) as dst:
    dst.write(arr, 1)
    dst.write_colormap(1, colormap)
print('Saved colormap GeoTIFF:', out_tif)
