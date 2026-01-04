import rasterio
import numpy as np
from PIL import Image

src = 'C:/coding/rasters/hazard_fused.tif'
out = 'C:/coding/rasters/hazard_fused_preview.png'

with rasterio.open(src) as s:
    a = s.read(1).astype('float32')
    mn = float(np.nanmin(a))
    mx = float(np.nanmax(a))
    if mx > mn:
        scaled = ((a - mn) * (255.0 / (mx - mn))).clip(0,255).astype('uint8')
    else:
        scaled = a.astype('uint8')

img = Image.fromarray(scaled)
img.save(out)
print('Saved preview:', out)
