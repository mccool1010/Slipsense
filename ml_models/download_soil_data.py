"""
download_soil_data.py
Downloads real soil property data from ISRIC SoilGrids v2.0 for the study area.
Covers S. Karnataka + N. Kerala (lon: 74.8–76.2, lat: 11.8–13.2, with buffer).

Downloads:
  - Clay content (0-5cm mean) → indicator of water retention & landslide susceptibility
  - Sand content (0-5cm mean) → inverse indicator (drainage capacity)

These are combined into a "Soil Susceptibility Index" raster that indicates
how prone the soil type is to becoming unstable when saturated.

Data source: ISRIC SoilGrids v2.0 (250m global resolution)
License: CC-BY 4.0
"""

import os
import sys
import numpy as np

try:
    import rasterio
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    from rasterio.transform import from_bounds
    import requests
    from scipy.ndimage import zoom as scipy_zoom
except ImportError as e:
    print(f"ERROR: Missing dependency: {e}")
    sys.exit(1)

# ---- CONFIG ----
RASTER_DIR = r"C:\coding\Slipsense\backend\rasters"
OUTPUT_CLAY = os.path.join(RASTER_DIR, "soil_clay_content.tif")
OUTPUT_SAND = os.path.join(RASTER_DIR, "soil_sand_content.tif")
OUTPUT_SOIL_INDEX = os.path.join(RASTER_DIR, "soil_susceptibility_index.tif")

# Study area bounds (WGS84) — with buffer around the actual raster extent
# Actual raster: lon=[75.0, 76.0], lat=[12.0, 13.0]
# Add buffer for edge effects during reprojection
BBOX_LON = (74.8, 76.2)
BBOX_LAT = (11.8, 13.2)

# SoilGrids REST API endpoint
SOILGRIDS_API = "https://rest.isric.org/soilgrids/v2.0/properties/query"

# Reference raster for alignment
REF_RASTER = os.path.join(RASTER_DIR, "susceptibility_dl.tif")


def download_soilgrids_grid(property_name: str, output_path: str, depth: str = "0-5cm"):
    """
    Download a soil property grid from SoilGrids API by sampling points
    across the study area and interpolating into a raster.
    
    This avoids GDAL vsicurl issues and works with any Python setup.
    """
    print(f"\n{'='*60}")
    print(f"Downloading {property_name} ({depth}) from SoilGrids API...")
    print(f"{'='*60}")
    
    # Create a grid of sample points across the study area
    # SoilGrids has 250m resolution ≈ 0.0025° at equator
    # We sample at ~0.05° intervals (every ~5km) and interpolate
    # This gives ~28 x 28 = ~784 points → manageable API load
    step = 0.05
    lons = np.arange(BBOX_LON[0], BBOX_LON[1] + step, step)
    lats = np.arange(BBOX_LAT[0], BBOX_LAT[1] + step, step)
    
    n_lons = len(lons)
    n_lats = len(lats)
    total_points = n_lons * n_lats
    
    print(f"Grid: {n_lons} x {n_lats} = {total_points} sample points")
    print(f"Longitude range: {lons[0]:.3f} to {lons[-1]:.3f}")
    print(f"Latitude range:  {lats[0]:.3f} to {lats[-1]:.3f}")
    
    # Initialize result array (lats descending for north-up raster)
    grid = np.full((n_lats, n_lons), np.nan, dtype=np.float32)
    
    # Query API point by point (with batching where possible)
    success_count = 0
    fail_count = 0
    
    from tqdm import tqdm
    
    total_queries = n_lats * n_lons
    pbar = tqdm(total=total_queries, desc=f"Fetching {property_name}")
    
    for i, lat in enumerate(reversed(lats)):  # reversed for north-up
        for j, lon in enumerate(lons):
            try:
                params = {
                    "lat": lat,
                    "lon": lon,
                    "property": property_name,
                    "depth": depth,
                    "value": "mean"
                }
                resp = requests.get(SOILGRIDS_API, params=params, timeout=10)
                
                if resp.status_code == 200:
                    data = resp.json()
                    # Parse the nested response
                    layers = data.get("properties", {}).get("layers", [])
                    if layers:
                        depths = layers[0].get("depths", [])
                        if depths:
                            values = depths[0].get("values", {})
                            mean_val = values.get("mean")
                            if mean_val is not None:
                                grid[i, j] = float(mean_val)
                                success_count += 1
                            else:
                                fail_count += 1
                        else:
                            fail_count += 1
                    else:
                        fail_count += 1
                elif resp.status_code == 404:
                    # Point is in ocean or no data
                    fail_count += 1
                else:
                    fail_count += 1
                    
            except Exception as e:
                fail_count += 1
            
            pbar.update(1)
    
    pbar.close()
    
    print(f"\nAPI results: {success_count} success, {fail_count} no-data/failed")
    print(f"Grid coverage: {(~np.isnan(grid)).mean()*100:.1f}%")
    
    if success_count == 0:
        print("ERROR: No data retrieved from API!")
        return False
    
    # Fill NaN gaps with nearest neighbor interpolation
    from scipy.ndimage import generic_filter
    
    # Simple fill: replace NaN with mean of non-NaN neighbors
    def fill_nan(arr):
        """Fill NaN values with interpolation."""
        from scipy.interpolate import griddata
        mask = ~np.isnan(arr)
        if mask.sum() == 0:
            return arr
        
        rows, cols = np.mgrid[0:arr.shape[0], 0:arr.shape[1]]
        points = np.column_stack((rows[mask], cols[mask]))
        values = arr[mask]
        
        filled = griddata(points, values, (rows, cols), method='nearest')
        return filled.astype(np.float32)
    
    grid_filled = fill_nan(grid)
    
    # Convert units: SoilGrids stores clay/sand as g/kg, divide by 10 for %
    grid_pct = grid_filled / 10.0
    
    print(f"Value range: {np.nanmin(grid_pct):.1f}% to {np.nanmax(grid_pct):.1f}%")
    print(f"Mean value: {np.nanmean(grid_pct):.1f}%")
    
    # Save as GeoTIFF in WGS84
    transform = from_bounds(BBOX_LON[0], BBOX_LAT[0], BBOX_LON[1], BBOX_LAT[1], n_lons, n_lats)
    
    profile = {
        'driver': 'GTiff',
        'dtype': 'float32',
        'width': n_lons,
        'height': n_lats,
        'count': 1,
        'crs': 'EPSG:4326',
        'transform': transform,
        'compress': 'lzw',
        'nodata': -9999,
    }
    
    with rasterio.open(output_path, 'w', **profile) as dst:
        dst.write(grid_pct, 1)
    
    print(f"Saved: {output_path}")
    return True


def create_soil_susceptibility_index():
    """
    Combine clay and sand content into a Soil Susceptibility Index.
    
    Formula:
    SSI = (clay_normalized × 0.6 + (1 - sand_normalized) × 0.4)
    
    Rationale:
    - High clay → holds water, becomes heavy and plastic → MORE prone to sliding
    - Low sand → poor drainage → MORE prone to saturation
    - This creates a 0–1 index where higher = more landslide-prone soil
    
    Then reproject and resample to match the susceptibility_dl raster.
    """
    print(f"\n{'='*60}")
    print("Creating Soil Susceptibility Index...")
    print(f"{'='*60}")
    
    # Load clay and sand
    with rasterio.open(OUTPUT_CLAY) as src:
        clay = src.read(1)
        clay_profile = src.profile.copy()
        clay_transform = src.transform
        clay_crs = src.crs
    
    with rasterio.open(OUTPUT_SAND) as src:
        sand = src.read(1)
    
    # Normalize to 0-1 range
    clay_min, clay_max = np.nanmin(clay[clay > 0]), np.nanmax(clay)
    sand_min, sand_max = np.nanmin(sand[sand > 0]), np.nanmax(sand)
    
    print(f"Clay range: {clay_min:.1f}% to {clay_max:.1f}%")
    print(f"Sand range: {sand_min:.1f}% to {sand_max:.1f}%")
    
    clay_norm = np.clip((clay - clay_min) / (clay_max - clay_min + 1e-6), 0, 1)
    sand_norm = np.clip((sand - sand_min) / (sand_max - sand_min + 1e-6), 0, 1)
    
    # Soil Susceptibility Index
    # High clay + Low sand = high susceptibility
    ssi = clay_norm * 0.6 + (1 - sand_norm) * 0.4
    
    # Handle nodata areas
    nodata_mask = (clay <= 0) | (sand <= 0)
    ssi[nodata_mask] = 0.5  # neutral value for unknown areas
    
    print(f"SSI range: {ssi.min():.3f} to {ssi.max():.3f}")
    print(f"SSI mean:  {ssi.mean():.3f}")
    
    # Save WGS84 version first
    ssi_wgs84_path = OUTPUT_SOIL_INDEX.replace('.tif', '_wgs84.tif')
    profile = clay_profile.copy()
    profile.update(dtype='float32', nodata=-9999)
    
    with rasterio.open(ssi_wgs84_path, 'w', **profile) as dst:
        dst.write(ssi.astype(np.float32), 1)
    
    print(f"Saved WGS84 SSI: {ssi_wgs84_path}")
    
    # Now reproject to match the reference raster (EPSG:32643)
    with rasterio.open(REF_RASTER) as ref:
        ref_transform = ref.transform
        ref_crs = ref.crs
        ref_width = ref.width
        ref_height = ref.height
    
    print(f"Reprojecting to {ref_crs} ({ref_width}x{ref_height})...")
    
    # Reproject
    dst_array = np.zeros((ref_height, ref_width), dtype=np.float32)
    
    with rasterio.open(ssi_wgs84_path) as src:
        reproject(
            source=src.read(1),
            destination=dst_array,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=ref_transform,
            dst_crs=ref_crs,
            resampling=Resampling.bilinear,
        )
    
    # Save final aligned version
    final_profile = {
        'driver': 'GTiff',
        'dtype': 'float32',
        'width': ref_width,
        'height': ref_height,
        'count': 1,
        'crs': ref_crs,
        'transform': ref_transform,
        'compress': 'lzw',
        'nodata': -9999,
    }
    
    with rasterio.open(OUTPUT_SOIL_INDEX, 'w', **final_profile) as dst:
        dst.write(dst_array, 1)
    
    print(f"Saved aligned SSI: {OUTPUT_SOIL_INDEX}")
    print(f"Shape: {dst_array.shape}, Range: [{dst_array.min():.3f}, {dst_array.max():.3f}]")
    
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("SoilGrids Data Downloader for SlipSense")
    print(f"Study area: lon={BBOX_LON}, lat={BBOX_LAT}")
    print("Source: ISRIC SoilGrids v2.0 (CC-BY 4.0)")
    print("=" * 60)
    
    # Step 1: Download clay content
    ok_clay = download_soilgrids_grid("clay", OUTPUT_CLAY, depth="0-5cm")
    
    # Step 2: Download sand content
    ok_sand = download_soilgrids_grid("sand", OUTPUT_SAND, depth="0-5cm")
    
    if ok_clay and ok_sand:
        # Step 3: Create combined index
        create_soil_susceptibility_index()
        
        print("\n" + "=" * 60)
        print("DONE! Soil rasters created:")
        print(f"  Clay content:  {OUTPUT_CLAY}")
        print(f"  Sand content:  {OUTPUT_SAND}")
        print(f"  Soil index:    {OUTPUT_SOIL_INDEX}")
        print("=" * 60)
    else:
        print("\nERROR: Failed to download one or more soil properties.")
        print("The SoilGrids REST API may be temporarily unavailable.")
        print("Try again later or check: https://www.isric.org/explore/soilgrids")
