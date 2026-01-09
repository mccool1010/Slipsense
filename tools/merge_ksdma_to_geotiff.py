"""
Merge KSDMA district-wise landslide susceptibility shapefiles into a single GeoTIFF.
Source: Kerala State Disaster Management Authority (KSDMA) - GSI 2022 data
"""

import os
import glob
import geopandas as gpd
import rasterio
from rasterio import features
from rasterio.transform import from_bounds
import numpy as np

# Configuration
DATA_DIR = r"c:\coding\Slipsense\data\ksdma_landslide_data"
OUTPUT_DIR = r"c:\coding\Slipsense\backend\rasters"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "susceptibility_historical_gsi.tif")
RESOLUTION = 0.00027  # ~30m resolution in degrees (matching SRTM DEM)

def find_shapefiles(data_dir):
    """Find all GSI landslide susceptibility shapefiles."""
    shapefiles = []
    for root, dirs, files in os.walk(data_dir):
        for f in files:
            if f.endswith('_GSI_LS.shp'):
                shapefiles.append(os.path.join(root, f))
    return shapefiles

def load_and_merge_shapefiles(shapefiles):
    """Load and merge all shapefiles into a single GeoDataFrame."""
    gdfs = []
    for shp in shapefiles:
        try:
            gdf = gpd.read_file(shp)
            district_name = os.path.basename(shp).replace('_GSI_LS.shp', '')
            gdf['district'] = district_name
            print(f"  Loaded {district_name}: {len(gdf)} features, CRS: {gdf.crs}")
            gdfs.append(gdf)
        except Exception as e:
            print(f"  Error loading {shp}: {e}")
    
    if not gdfs:
        raise ValueError("No shapefiles could be loaded")
    
    merged = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True))
    print(f"\nTotal merged features: {len(merged)}")
    return merged

def analyze_attributes(gdf):
    """Analyze the attribute structure of the data."""
    print("\n=== Attribute Analysis ===")
    print(f"Columns: {list(gdf.columns)}")
    
    # Print sample attributes
    if len(gdf) > 0:
        print("\nSample row:")
        print(gdf.iloc[0])
        
        # Check for susceptibility classification column
        for col in gdf.columns:
            if col != 'geometry' and col != 'district':
                print(f"\n{col} unique values: {gdf[col].unique()[:10]}")
    
    return gdf

def rasterize_to_geotiff(gdf, output_path, resolution):
    """Convert vector data to GeoTIFF raster."""
    print("\n=== Rasterization ===")
    
    # Reproject to WGS84 (EPSG:4326) if needed
    if gdf.crs != 'EPSG:4326':
        print(f"Reprojecting from {gdf.crs} to EPSG:4326...")
        gdf = gdf.to_crs('EPSG:4326')
    
    # Get bounds
    bounds = gdf.total_bounds  # (minx, miny, maxx, maxy)
    print(f"Bounds: {bounds}")
    
    # Calculate dimensions
    width = int((bounds[2] - bounds[0]) / resolution)
    height = int((bounds[3] - bounds[1]) / resolution)
    print(f"Output dimensions: {width} x {height} pixels")
    
    # Create transform
    transform = from_bounds(bounds[0], bounds[1], bounds[2], bounds[3], width, height)
    
    # Determine the value column for susceptibility
    # Look for common susceptibility column names
    value_col = None
    for col in ['susc_class', 'class', 'Class', 'LH_Class', 'Zone', 'ZONE', 'Suscept', 'SUSCEPT', 'LS_Class', 'gridcode']:
        if col in gdf.columns:
            value_col = col
            break
    
    if value_col is None:
        # Use all non-geometry columns
        non_geom_cols = [c for c in gdf.columns if c != 'geometry' and c != 'district']
        if non_geom_cols:
            value_col = non_geom_cols[0]
            print(f"Using column '{value_col}' for rasterization")
    
    # Create shapes for rasterization
    if value_col:
        # Map string values to numeric if needed
        if gdf[value_col].dtype == 'object':
            unique_vals = gdf[value_col].unique()
            print(f"Mapping {value_col} values: {unique_vals}")
            
            # Create mapping based on common susceptibility terms
            value_map = {}
            for i, val in enumerate(sorted(unique_vals), 1):
                val_lower = str(val).lower() if val else ''
                if 'very high' in val_lower:
                    value_map[val] = 5
                elif 'high' in val_lower:
                    value_map[val] = 4
                elif 'moderate' in val_lower or 'medium' in val_lower:
                    value_map[val] = 3
                elif 'low' in val_lower and 'very' not in val_lower:
                    value_map[val] = 2
                elif 'very low' in val_lower:
                    value_map[val] = 1
                else:
                    value_map[val] = i
            
            print(f"Value mapping: {value_map}")
            gdf['_raster_value'] = gdf[value_col].map(value_map)
            shapes = ((geom, value) for geom, value in zip(gdf.geometry, gdf['_raster_value']) if value is not None)
        else:
            shapes = ((geom, value) for geom, value in zip(gdf.geometry, gdf[value_col]))
    else:
        # Default: use 1 for all features (presence/absence)
        print("No value column found, using presence/absence (1)")
        shapes = ((geom, 1) for geom in gdf.geometry)
    
    # Rasterize
    print("Rasterizing...")
    raster = features.rasterize(
        shapes,
        out_shape=(height, width),
        transform=transform,
        fill=0,  # NoData
        dtype=np.uint8
    )
    
    # Write GeoTIFF
    print(f"Writing to {output_path}...")
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
        
        # Add colormap for visualization
        colormap = {
            0: (255, 255, 255, 0),    # NoData - transparent
            1: (0, 128, 0, 255),       # Very Low - green
            2: (144, 238, 144, 255),   # Low - light green
            3: (255, 255, 0, 255),     # Moderate - yellow
            4: (255, 165, 0, 255),     # High - orange
            5: (255, 0, 0, 255),       # Very High - red
        }
        dst.write_colormap(1, colormap)
    
    print(f"Successfully created: {output_path}")
    print(f"File size: {os.path.getsize(output_path) / (1024*1024):.2f} MB")
    
    # Print statistics
    unique, counts = np.unique(raster, return_counts=True)
    print("\nPixel value distribution:")
    for value, count in zip(unique, counts):
        pct = count / raster.size * 100
        print(f"  Value {value}: {count:,} pixels ({pct:.2f}%)")

def main():
    import pandas as pd  # Import here to avoid globals issue
    
    print("KSDMA Landslide Susceptibility Data Processing")
    print("=" * 50)
    
    # Find shapefiles
    print("\n1. Finding shapefiles...")
    shapefiles = find_shapefiles(DATA_DIR)
    print(f"Found {len(shapefiles)} shapefiles:")
    for shp in shapefiles:
        print(f"  - {os.path.basename(shp)}")
    
    if not shapefiles:
        print("ERROR: No shapefiles found!")
        return
    
    # Load and merge
    print("\n2. Loading and merging shapefiles...")
    gdf = load_and_merge_shapefiles(shapefiles)
    
    # Analyze
    print("\n3. Analyzing attributes...")
    gdf = analyze_attributes(gdf)
    
    # Rasterize
    print("\n4. Converting to GeoTIFF...")
    rasterize_to_geotiff(gdf, OUTPUT_FILE, RESOLUTION)
    
    print("\n" + "=" * 50)
    print("Processing complete!")
    print(f"Output file: {OUTPUT_FILE}")

if __name__ == "__main__":
    import pandas as pd
    main()
