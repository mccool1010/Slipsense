import rasterio
import numpy as np

paths = {
    'transit':'C:/coding/rasters/transit_mask.tif',
    'deposition':'C:/coding/rasters/deposition_mask.tif',
    'fused':'C:/coding/rasters/hazard_fused.tif'
}

for name,p in paths.items():
    print('\n---', name, p)
    try:
        with rasterio.open(p) as src:
            arr = src.read(1)
            print('dtype:', arr.dtype)
            print('shape:', arr.shape)
            print('count bands:', src.count)
            print('crs:', src.crs)
            print('transform:', src.transform)
            print('nodata:', src.nodatavals)
            print('min, max:', np.nanmin(arr), np.nanmax(arr))
            nonzero = np.count_nonzero(arr)
            total = arr.size
            print('non-zero count:', nonzero, f'({nonzero/total*100:.4f}%)')
            # unique values and counts (safe for small number of unique values)
            vals,counts = np.unique(arr, return_counts=True)
            print('unique values:', vals)
            print('counts (first 10):', list(zip(vals, counts))[:10])
    except Exception as e:
        print('ERROR reading', p, e)

print('\nDone')
