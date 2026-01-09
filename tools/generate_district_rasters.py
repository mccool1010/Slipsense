"""
Generate per-district landslide susceptibility GeoTIFFs from KSDMA shapefiles.
Each district gets its own raster file for filtering in the web application.
"""

import os
import geopandas as gpd
import rasterio
from rasterio import features
from rasterio.transform import from_bounds
import numpy as np

# Configuration
DATA_DIR = r"c:\coding\Slipsense\data\ksdma_landslide_data"
OUTPUT_DIR = r"c:\coding\Slipsense\backend\rasters\districts"
RESOLUTION = 0.00027  # ~30m resolution in degrees

# District name mapping (folder name -> canonical name)
DISTRICT_FOLDERS = {
    "TVM": "thiruvananthapuram",
    "Kollam": "kollam",
    "Pathanamthitta": "pathanamthitta",
    "Kottayam": "kottayam",
    "Idukki": "idukki",
    "Ernakulam": "ernakulam",
    "Thrissur": "thrissur",
    "Palakkad": "palakkad",
    "Malappuram": "malappuram",
    "Kozhikode": "kozhikode",
    "Wayanad": "wayanad",
    "Kannur": "kannur",
    "Kasaragod": "kasaragod",
}

def find_shapefile(folder_path):
    """Find the GSI_LS shapefile in a district folder."""
    for root, dirs, files in os.walk(folder_path):
        for f in files:
            if f.endswith('_GSI_LS.shp'):
                return os.path.join(root, f)
    return None

def rasterize_district(gdf, output_path, resolution):
    """Convert a single district's vector data to GeoTIFF."""
    
    # Reproject to WGS84 if needed
    if gdf.crs != 'EPSG:4326':
        gdf = gdf.to_crs('EPSG:4326')
    
    # Get bounds
    bounds = gdf.total_bounds  # (minx, miny, maxx, maxy)
    
    # Calculate dimensions
    width = max(1, int((bounds[2] - bounds[0]) / resolution))
    height = max(1, int((bounds[3] - bounds[1]) / resolution))
    
    print(f"    Bounds: {bounds}")
    print(f"    Dimensions: {width} x {height} pixels")
    
    # Create transform
    transform = from_bounds(bounds[0], bounds[1], bounds[2], bounds[3], width, height)
    
    # Look for susceptibility column
    value_col = None
    for col in ['Susceptibi', 'susc_class', 'class', 'Class', 'Zone']:
        if col in gdf.columns:
            value_col = col
            break
    
    if value_col is None:
        non_geom_cols = [c for c in gdf.columns if c != 'geometry']
        if non_geom_cols:
            value_col = non_geom_cols[0]
    
    print(f"    Using column: {value_col}")
    
    # Map string values to numeric
    if gdf[value_col].dtype == 'object':
        unique_vals = gdf[value_col].unique()
        value_map = {}
        for val in unique_vals:
            val_lower = str(val).lower() if val else ''
            if 'high' in val_lower:
                value_map[val] = 4
            elif 'moderate' in val_lower or 'medium' in val_lower:
                value_map[val] = 3
            elif 'low' in val_lower:
                value_map[val] = 2
            else:
                value_map[val] = 1
        
        print(f"    Value mapping: {value_map}")
        gdf['_raster_value'] = gdf[value_col].map(value_map)
        shapes = [(geom, value) for geom, value in zip(gdf.geometry, gdf['_raster_value']) if value is not None]
    else:
        shapes = [(geom, value) for geom, value in zip(gdf.geometry, gdf[value_col])]
    
    # Rasterize
    raster = features.rasterize(
        shapes,
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype=np.uint8
    )
    
    # Write GeoTIFF
    with rasterio.open(
        output_path,
        'w',
        driver='GTiff',
        height=height,
        width=width,
        count=1,
        dtype=np.uint8,
        crs='EPSG:4326',
        transform=transform,
        nodata=0,
        compress='LZW'
    ) as dst:
        dst.write(raster, 1)
    
    file_size = os.path.getsize(output_path) / 1024
    print(f"    Created: {os.path.basename(output_path)} ({file_size:.1f} KB)")
    
    return True

def main():
    print("Generating Per-District Landslide Susceptibility Rasters")
    print("=" * 60)
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Output directory: {OUTPUT_DIR}\n")
    
    success_count = 0
    
    for folder_name, canonical_name in DISTRICT_FOLDERS.items():
        print(f"Processing {folder_name} -> {canonical_name}...")
        
        folder_path = os.path.join(DATA_DIR, folder_name)
        if not os.path.exists(folder_path):
            print(f"  [SKIP] Folder not found: {folder_path}")
            continue
        
        shapefile = find_shapefile(folder_path)
        if not shapefile:
            print(f"  [SKIP] No shapefile found in {folder_path}")
            continue
        
        try:
            gdf = gpd.read_file(shapefile)
            print(f"    Loaded {len(gdf)} features from {os.path.basename(shapefile)}")
            
            output_path = os.path.join(OUTPUT_DIR, f"susceptibility_{canonical_name}.tif")
            rasterize_district(gdf, output_path, RESOLUTION)
            success_count += 1
            
        except Exception as e:
            print(f"  [ERROR] {e}")
    
    print("\n" + "=" * 60)
    print(f"Successfully created {success_count} district rasters")
    print(f"Output location: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
