"""
generate_runout_and_fuse.py
Produces runout paths (D8 based) and fused hazard map from DL susceptibility.
Uses historical GSI/KSDMA susceptibility data as calibration reference.
Put this script in any folder and run with Python in your venv.
"""

import os
import json
import numpy as np
import sys
try:
    import rasterio
    from rasterio.features import rasterize
    from shapely.geometry import LineString, mapping
    from scipy.ndimage import binary_dilation
    from scipy import ndimage as ndi
    from tqdm import tqdm
except Exception as e:
    print("ERROR: missing dependency or failed import:", e)
    print("- If you're using a virtual environment, run the script with that venv's Python.")
    print("  Example (PowerShell):")
    print("    & 'c:\\coding\\Slipsense\\ml_models\\my_venv_3_12\\Scripts\\python.exe' ")
    print("      'c:\\coding\\Slipsense\\ml_models\\generate_runout_and_fuse.py'")
    print("- Or install requirements from `ml_models/requirements.txt` into your active Python.")
    sys.exit(1)

# ---------------- CONFIG - adapt if needed ----------------
RASTER_DIR = r"C:\coding\Slipsense\backend\rasters"

DEM_TIF = os.path.join(RASTER_DIR, "DEM_filled_75.tif")
SUS_DL_TIF = os.path.join(RASTER_DIR, "susceptibility_dl.tif")
FLOW_ACC_TIF = os.path.join(RASTER_DIR, "Flow_Accumulation_clean75.tif")
SLOPE_TIF = os.path.join(RASTER_DIR, "slope75.tif")
HIST_TIF = os.path.join(RASTER_DIR, "susceptibility_historical_gsi.tif")
SOIL_TIF = os.path.join(RASTER_DIR, "soil_susceptibility_index.tif")

OUT_RUNOUT_GEOJSON = os.path.join(RASTER_DIR, "runout_paths.geojson")
OUT_TRANSIT = os.path.join(RASTER_DIR, "transit_mask.tif")
OUT_DEPOSITION = os.path.join(RASTER_DIR, "deposition_mask.tif")
OUT_FUSED = os.path.join(RASTER_DIR, "hazard_fused.tif")

# thresholds & params — calibrated with historical GSI + soil reference
THRESH_HIGH = 0.80               # blended susceptibility >= this => failure
STREAM_ACC_THRESH = 8000         # flow accumulation considered stream (higher = longer paths)
SLOPE_DEPOSITION_MAX = 20        # deposition on slopes < 20° (computed from DEM)
TRANSIT_BUFFER_PIX = 5           # transit corridor buffer (wider for visibility)
MIN_SOURCE_PIXELS = 15           # keep smaller source clusters
DEPOSITION_BUFFER_PIX = 6        # deposition fan radius (~180m at 30m pixels)
DEPOSITION_TAIL_PIXELS = 5       # last 5 pixels of each path as seeds
HIST_WEIGHT = 0.30               # blending weight for historical data
SOIL_WEIGHT = 0.15               # blending weight for soil susceptibility

# ---------------- Helpers ----------------
def fd_to_offset(val):
    """
    Convert a D8 flow-direction value to (dr,dc) movement offsets.
    Supports both bitmask values (1,2,4,..128) and 0..7 index codes.
    """
    # bitmask mapping (common encoding: 1=E,2=SE,4=S,8=SW,16=W,32=NW,64=N,128=NE)
    mapping_bit = {
        1: (0, 1),
        2: (1, 1),
        4: (1, 0),
        8: (1, -1),
        16: (0, -1),
        32: (-1, -1),
        64: (-1, 0),
        128:(-1, 1)
    }
    # index mapping (0..7) assumed as [E,NE,N,NW,W,SW,S,SE]
    mapping_idx = {
        0: (0,1), 1:(-1,1), 2:(-1,0), 3:(-1,-1),
        4:(0,-1), 5:(1,-1), 6:(1,0), 7:(1,1)
    }
    if val in mapping_bit:
        return mapping_bit[val]
    if val in mapping_idx:
        return mapping_idx[val]
    # sometimes richdem uses powers-of-two as ints but not exactly those values:
    # try to detect power-of-two
    try:
        v = int(val)
        if v > 0 and (v & (v-1)) == 0:
            # find which bit
            for k,off in mapping_bit.items():
                if k == v:
                    return off
    except Exception:
        pass
    return None

# ---------------- Load data ----------------
print("Loading rasters...")
with rasterio.open(DEM_TIF) as src:
    dem_profile = src.profile.copy()
    dem = src.read(1).astype(np.float32)

with rasterio.open(SUS_DL_TIF) as src:
    sus = src.read(1).astype(np.float32)
    sus_profile = src.profile.copy()

with rasterio.open(FLOW_ACC_TIF) as src:
    flow_acc = src.read(1).astype(np.float32)

with rasterio.open(SLOPE_TIF) as src:
    slope_raw = src.read(1).astype(np.float32)

h, w = sus.shape
transform = sus_profile['transform']
crs = sus_profile.get('crs', None)

print(f"Raster size (reference = susceptibility): {w} x {h}")
print(f"  DEM shape: {dem.shape}, Slope_raw shape: {slope_raw.shape}, Flow_acc shape: {flow_acc.shape}")

# Resize all rasters to match susceptibility dimensions if needed
from scipy.ndimage import zoom as scipy_zoom

if dem.shape != (h, w):
    print(f"  Resizing DEM from {dem.shape} to ({h}, {w})")
    dem = scipy_zoom(dem, (h / dem.shape[0], w / dem.shape[1]), order=1)

if slope_raw.shape != (h, w):
    print(f"  Resizing slope_raw from {slope_raw.shape} to ({h}, {w})")
    slope_raw = scipy_zoom(slope_raw, (h / slope_raw.shape[0], w / slope_raw.shape[1]), order=1)

if flow_acc.shape != (h, w):
    print(f"  Resizing flow_acc from {flow_acc.shape} to ({h}, {w})")
    flow_acc = scipy_zoom(flow_acc, (h / flow_acc.shape[0], w / flow_acc.shape[1]), order=1)

# Compute slope directly from DEM (the slope75.tif has broken values ~90° everywhere)
# This gives reliable slope in degrees for deposition filtering
print("Computing slope from DEM (gradient-based)...")
cell_size = abs(transform.a)  # pixel size in meters
dy, dx = np.gradient(dem, cell_size)
slope = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))
print(f"  Computed slope: min={slope.min():.1f}°, max={slope.max():.1f}°, mean={slope.mean():.1f}°")
print(f"  % pixels <= {SLOPE_DEPOSITION_MAX}°: {(slope <= SLOPE_DEPOSITION_MAX).mean()*100:.1f}%")

# ---- Load historical GSI susceptibility as calibration reference ----
print("Loading historical susceptibility (GSI/KSDMA)...")
try:
    with rasterio.open(HIST_TIF) as src:
        hist_raw = src.read(1).astype(np.float32)
        # Resize if dimensions differ from susceptibility raster
        if hist_raw.shape != (h, w):
            from scipy.ndimage import zoom as scipy_zoom
            zoom_factors = (h / hist_raw.shape[0], w / hist_raw.shape[1])
            hist_raw = scipy_zoom(hist_raw, zoom_factors, order=0)  # nearest-neighbor for classes
            print(f"  Resized historical from original to ({h}, {w})")
    print(f"  Historical raster loaded. Unique values: {np.unique(hist_raw)}")
except Exception as e:
    print(f"WARNING: Could not load historical raster ({e}). Using pure DL susceptibility.")
    hist_raw = np.zeros((h, w), dtype=np.float32)

# Normalize GSI classes to continuous 0-1 scale:
#   0 (NoData) → 0.0,  2 (Low) → 0.25,  3 (Moderate) → 0.55,  4 (High) → 1.0
hist_norm = np.zeros_like(hist_raw, dtype=np.float32)
hist_norm[hist_raw == 2] = 0.25
hist_norm[hist_raw == 3] = 0.55
hist_norm[hist_raw == 4] = 1.0

# Create history-calibrated blended susceptibility
has_hist = (hist_raw > 0).astype(np.float32)  # 1 where GSI data exists

hist_coverage = has_hist.mean() * 100
print(f"  Historical coverage: {hist_coverage:.1f}% of pixels")

# ---- Load soil susceptibility index (SoilGrids clay/sand) ----
print("Loading soil susceptibility index (SoilGrids)...")
try:
    with rasterio.open(SOIL_TIF) as src:
        soil_raw = src.read(1).astype(np.float32)
        if soil_raw.shape != (h, w):
            zoom_factors = (h / soil_raw.shape[0], w / soil_raw.shape[1])
            soil_raw = scipy_zoom(soil_raw, zoom_factors, order=1)
            print(f"  Resized soil from original to ({h}, {w})")
    # Clean nodata values
    soil_raw[soil_raw < 0] = 0
    soil_raw[soil_raw > 1] = 1
    has_soil = (soil_raw > 0).astype(np.float32)
    soil_coverage = has_soil.mean() * 100
    print(f"  Soil raster loaded. Range: [{soil_raw.min():.3f}, {soil_raw.max():.3f}]")
    print(f"  Soil coverage: {soil_coverage:.1f}% of pixels")
except Exception as e:
    print(f"WARNING: Could not load soil raster ({e}). Proceeding without soil data.")
    soil_raw = np.zeros((h, w), dtype=np.float32)
    has_soil = np.zeros((h, w), dtype=np.float32)

# Create blended susceptibility: DL + Historical GSI + Soil
# Weights are normalized based on what data is available at each pixel:
#   Both hist+soil: DL × 0.55 + GSI × 0.30 + Soil × 0.15
#   Hist only:      DL × 0.70 + GSI × 0.30
#   Soil only:      DL × 0.85 + Soil × 0.15  
#   Neither:        DL × 1.00
sus_blended = sus.copy()

# Pixels with both historical AND soil data
both_mask = (has_hist > 0) & (has_soil > 0)
sus_blended[both_mask] = (
    sus[both_mask] * (1 - HIST_WEIGHT - SOIL_WEIGHT) +
    hist_norm[both_mask] * HIST_WEIGHT +
    soil_raw[both_mask] * SOIL_WEIGHT
)

# Pixels with only historical data
hist_only_mask = (has_hist > 0) & (has_soil <= 0)
sus_blended[hist_only_mask] = (
    sus[hist_only_mask] * (1 - HIST_WEIGHT) +
    hist_norm[hist_only_mask] * HIST_WEIGHT
)

# Pixels with only soil data
soil_only_mask = (has_hist <= 0) & (has_soil > 0)
sus_blended[soil_only_mask] = (
    sus[soil_only_mask] * (1 - SOIL_WEIGHT) +
    soil_raw[soil_only_mask] * SOIL_WEIGHT
)

print(f"  Susceptibility stats — DL mean: {sus.mean():.3f}, Blended mean: {sus_blended.mean():.3f}")

# ---------------- Compute D8 flow-direction ----------------
print("Computing D8 flow direction... (this may take a moment)")
# Simple D8 flow direction: find steepest descent neighbor
# Returns bitmask: 1=E,2=SE,4=S,8=SW,16=W,32=NW,64=N,128=NE
fd_np = np.zeros((h, w), dtype=np.int32)

# D8 offsets: (dr, dc) -> bitmask value
d8_offsets = [
    (0, 1, 1),    # E
    (1, 1, 2),    # SE
    (1, 0, 4),    # S
    (1, -1, 8),   # SW
    (0, -1, 16),  # W
    (-1, -1, 32), # NW
    (-1, 0, 64),  # N
    (-1, 1, 128)  # NE
]

for r in tqdm(range(h), desc="Computing D8 flow direction"):
    for c in range(w):
        curr_elev = dem[r, c]
        max_slope = 0
        best_dir = 0
        
        for dr, dc, bitmask in d8_offsets:
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w:
                neighbor_elev = dem[nr, nc]
                dist = np.sqrt(dr**2 + dc**2)  # diagonal vs cardinal distance
                slope_val = (curr_elev - neighbor_elev) / dist
                if slope_val > max_slope and neighbor_elev < curr_elev:
                    max_slope = slope_val
                    best_dir = bitmask
        
        fd_np[r, c] = best_dir

# ---- Build cleaned list of source points from blended susceptibility ----
# Use blended (history-calibrated) susceptibility for source detection
source_mask = (sus_blended >= THRESH_HIGH).astype(np.uint8)

# morphological opening to remove very small noise
structure = np.ones((3, 3), dtype=np.uint8)
source_mask = ndi.binary_opening(source_mask, structure=structure).astype(np.uint8)

# label connected components
labeled, ncomp = ndi.label(source_mask)
component_sizes = np.bincount(labeled.ravel())
# zero label is background, so component_sizes[0] is background count
keep_labels = np.where(component_sizes >= MIN_SOURCE_PIXELS)[0].tolist()
# remove background label=0 from keep set (if present)
if 0 in keep_labels:
    keep_labels.remove(0)

# build list of source centroids (one per kept component)
sources = []
for lab in keep_labels:
    coords = np.column_stack(np.where(labeled == lab))  # rows, cols
    if coords.size == 0:
        continue
    # centroid in pixel coordinates (row, col)
    r_mean = int(np.round(coords[:, 0].mean()))
    c_mean = int(np.round(coords[:, 1].mean()))
    sources.append((r_mean, c_mean))

print(f"Original source pixels: {np.sum(source_mask)}. Components kept: {len(sources)}")

# ---------------- Trace runout paths ----------------
print("Tracing runout paths (following D8 pointers)...")
visited_mask = np.zeros_like(sus, dtype=np.uint8)
runout_lines = []
deposition_seeds = np.zeros((h, w), dtype=np.uint8)  # endpoints for deposition

for (r,c) in tqdm(sources):
    path = [(c, r)]          # (col, row) for map coords
    path_pixels = [(r, c)]   # (row, col) for raster indexing
    rr, cc = r, c
    steps = 0
    max_steps = max(h,w) * 10
    while True:
        steps += 1
        if steps > max_steps:
            break
        val = int(fd_np[rr, cc])
        off = fd_to_offset(val)
        if off is None:
            break
        dr, dc = off
        nr, nc = rr + dr, cc + dc
        # stop if outside
        if not (0 <= nr < h and 0 <= nc < w):
            break
        path.append((nc, nr))
        path_pixels.append((nr, nc))
        # stop if we reached stream (flow accumulation) or edge
        if flow_acc[nr, nc] >= STREAM_ACC_THRESH:
            break
        # stop if loop or visited
        if visited_mask[nr, nc]:
            break
        rr, cc = nr, nc
        visited_mask[rr, cc] = 1
    if len(path) > 1:
        # Mark the last N pixels of the path as deposition seeds (not just the endpoint)
        tail = path_pixels[-DEPOSITION_TAIL_PIXELS:]
        for (tr, tc) in tail:
            if 0 <= tr < h and 0 <= tc < w:
                deposition_seeds[tr, tc] = 1
        # convert pixel coords to map coords using transform (col,row -> x,y)
        map_coords = [((col * transform.a) + transform.c, (row * transform.e) + transform.f) for (col,row) in path]
        runout_lines.append(LineString(map_coords))

print("Runout paths created:", len(runout_lines))
print("Deposition seed pixels:", np.sum(deposition_seeds))

# Transform from raster CRS to WGS84 (EPSG:4326)
print("Transforming coordinates to WGS84...")
try:
    from pyproj import Transformer
    
    if crs is None:
        print("WARNING: Raster has no CRS information. Assuming coordinates are already in WGS84.")
        transformed_lines = runout_lines
    else:
        # Create transformer from raster CRS to WGS84
        transformer = Transformer.from_crs(crs, 'EPSG:4326', always_xy=True)
        transformed_lines = []
        for line in runout_lines:
            # Get coordinates and transform them (always_xy=True means input is (x,y))
            coords = list(line.coords)
            # coords are (x, y) from map projection, transform to (lon, lat)
            transformed_coords = [transformer.transform(x, y) for x, y in coords]
            transformed_lines.append(LineString(transformed_coords))
        print(f"Transformed {len(transformed_lines)} lines to WGS84")
except Exception as e:
    print(f"WARNING: CRS transformation failed ({e}). Using original coordinates.")
    transformed_lines = runout_lines

# Use transformed lines for GeoJSON
runout_lines_geojson = transformed_lines

# ---------------- Save runout geojson ----------------
print("Saving runout geojson:", OUT_RUNOUT_GEOJSON)
features = [{"type":"Feature","geometry": mapping(line), "properties": {"id": i}} for i, line in enumerate(runout_lines_geojson)]
geo = {"type":"FeatureCollection", "features": features, "crs": {"type": "name", "properties": {"name": "EPSG:4326"}}}
with open(OUT_RUNOUT_GEOJSON, "w") as f:
    json.dump(geo, f)

# ---------------- Rasterize runout into mask ----------------
print("Rasterizing runout lines to mask...")
if len(runout_lines) == 0:
    runout_mask = np.zeros((h,w), dtype=np.uint8)
else:
    shapes_iter = ((mapping(geom), 1) for geom in runout_lines)
    runout_mask = rasterize(shapes_iter, out_shape=(h,w), transform=transform, fill=0, dtype='uint8')

# ---------------- Transit mask (tighter buffer along runout paths) ----------------
print("Creating transit mask...")
struct = np.ones((TRANSIT_BUFFER_PIX*2 + 1, TRANSIT_BUFFER_PIX*2 + 1), dtype=bool)
transit_mask = binary_dilation(runout_mask, structure=struct).astype(np.uint8)
print(f"  Transit pixels: {np.sum(transit_mask)} ({np.sum(transit_mask)/transit_mask.size*100:.2f}%)")

# ---------------- Deposition mask (endpoint-based fans) ----------------
print("Computing deposition mask from runout endpoints...")
print(f"  Deposition seed pixels: {np.sum(deposition_seeds)}")
# Dilate endpoint seeds into deposition fans (circular, not square)
fan_radius = DEPOSITION_BUFFER_PIX
y, x = np.ogrid[-fan_radius:fan_radius+1, -fan_radius:fan_radius+1]
dep_struct = (x**2 + y**2 <= fan_radius**2).astype(bool)  # circular disk
deposition_raw = binary_dilation(deposition_seeds, structure=dep_struct).astype(np.uint8)
print(f"  After dilation (before slope filter): {np.sum(deposition_raw)} pixels")
# Constrain to moderate/gentle terrain (debris deposits where slope decreases)
deposition_slope_ok = ((deposition_raw == 1) & (slope <= SLOPE_DEPOSITION_MAX)).astype(np.uint8)
print(f"  After slope filter (<= {SLOPE_DEPOSITION_MAX}°): {np.sum(deposition_slope_ok)} pixels")
# Use slope-filtered if non-empty, otherwise use raw dilation as fallback
if np.sum(deposition_slope_ok) > 0:
    deposition_mask = deposition_slope_ok
else:
    print(f"  WARNING: Slope filter removed all deposition. Using dilated endpoints directly.")
    deposition_mask = deposition_raw
print(f"  Final deposition pixels: {np.sum(deposition_mask)} ({np.sum(deposition_mask)/deposition_mask.size*100:.2f}%)")

# ---------------- Fusion (Deposition → Transit → Failure) ----------------
print("Fusing into final hazard raster (codes: 3=Failure, 2=Transit, 1=Deposition, 0=Safe)...")
fused = np.zeros_like(sus, dtype=np.uint8)

# 1. Paint deposition FIRST — runout endpoints on flat ground get visibility
fused[deposition_mask == 1] = 1

# 2. Paint transit — runout corridors on steep terrain
fused[(transit_mask == 1) & (fused == 0)] = 2

# 3. Paint failure LAST — high blended susceptibility overrides everything
#    (a pixel with very high calibrated susceptibility IS a failure zone)
fused[sus_blended >= THRESH_HIGH] = 3

# ---- Diagnostic stats ----
vals, counts = np.unique(fused, return_counts=True)
total = fused.size
print("\n=== Fused Hazard Map Statistics ===")
for v, c in zip(vals, counts):
    label = {0: "Safe", 1: "Deposition", 2: "Transit", 3: "Failure"}.get(v, "?")
    print(f"  {label} (code={v}): {c:,} pixels ({c/total*100:.2f}%)")
print()

# ---------------- Save outputs ----------------
meta = sus_profile.copy()
meta.update(dtype=rasterio.uint8, count=1, compress='lzw', nodata=None)

print("Saving transit mask:", OUT_TRANSIT)
with rasterio.open(OUT_TRANSIT, "w", **meta) as dst:
    dst.write(transit_mask.astype('uint8'), 1)

print("Saving deposition mask:", OUT_DEPOSITION)
with rasterio.open(OUT_DEPOSITION, "w", **meta) as dst:
    dst.write(deposition_mask.astype('uint8'), 1)

print("Saving fused hazard map:", OUT_FUSED)
with rasterio.open(OUT_FUSED, "w", **meta) as dst:
    dst.write(fused.astype('uint8'), 1)

print("All done. Outputs:")
print(" - Runout GeoJSON:", OUT_RUNOUT_GEOJSON)
print(" - Transit mask:", OUT_TRANSIT)
print(" - Deposition mask:", OUT_DEPOSITION)
print(" - Fused hazard map:", OUT_FUSED)
