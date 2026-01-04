"""
generate_runout_and_fuse.py
Produces runout paths (D8 based) and fused hazard map from DL susceptibility.
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

OUT_RUNOUT_GEOJSON = os.path.join(RASTER_DIR, "runout_paths.geojson")
OUT_TRANSIT = os.path.join(RASTER_DIR, "transit_mask.tif")
OUT_DEPOSITION = os.path.join(RASTER_DIR, "deposition_mask.tif")
OUT_FUSED = os.path.join(RASTER_DIR, "hazard_fused.tif")

# thresholds & params (tune if necessary)
THRESH_HIGH = 0.25               # susceptibility >= this => source/failure
STREAM_ACC_THRESH = 5000        # flow accumulation value considered stream (tune)
DEPOSITION_ACC_FACTOR = 2       # deposition if flow_acc > STREAM_ACC_THRESH * factor
SLOPE_DEPOSITION_MAX = 15       # slope (degrees) threshold for deposition
TRANSIT_BUFFER_PIX = 5          # buffer radius in pixels for transit zone
MIN_SOURCE_PIXELS = 10          # remove small components below this pixel count

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
    slope = src.read(1).astype(np.float32)

h, w = sus.shape
transform = sus_profile['transform']
crs = sus_profile.get('crs', None)

print(f"Raster size: {w} x {h}")

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
                slope = (curr_elev - neighbor_elev) / dist
                if slope > max_slope and neighbor_elev < curr_elev:
                    max_slope = slope
                    best_dir = bitmask
        
        fd_np[r, c] = best_dir

# ---- New: build cleaned list of source points from DL susceptibility ----
# stricter threshold for initiation and remove tiny speckles
source_mask = (sus >= THRESH_HIGH).astype(np.uint8)

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

for (r,c) in tqdm(sources):
    path = [(c, r)]
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
        # stop if we reached stream (flow accumulation) or edge
        if flow_acc[nr, nc] >= STREAM_ACC_THRESH:
            break
        # stop if loop or visited
        if visited_mask[nr, nc]:
            break
        rr, cc = nr, nc
        visited_mask[rr, cc] = 1
    if len(path) > 1:
        # convert pixel coords to map coords using transform (col,row -> x,y)
        map_coords = [((col * transform.a) + transform.c, (row * transform.e) + transform.f) for (col,row) in path]
        runout_lines.append(LineString(map_coords))

print("Runout paths created:", len(runout_lines))

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

# ---------------- Transit mask (buffered runout) ----------------
print("Creating transit mask by dilating runout...")
struct = np.ones((TRANSIT_BUFFER_PIX*2 + 1, TRANSIT_BUFFER_PIX*2 + 1), dtype=bool)
transit_mask = binary_dilation(runout_mask, structure=struct).astype(np.uint8)

# ---------------- Deposition mask ----------------
print("Computing deposition mask...")
deposition_cond = (flow_acc >= (STREAM_ACC_THRESH * DEPOSITION_ACC_FACTOR)) & (slope <= SLOPE_DEPOSITION_MAX)
deposition_mask = np.zeros_like(sus, dtype=np.uint8)
deposition_mask[deposition_cond & (transit_mask==1)] = 1

# ---------------- Fusion ----------------
print("Fusing into final hazard raster (codes: 3=Failure,2=Transit,1=Deposition,0=Safe)...")
fused = np.zeros_like(sus, dtype=np.uint8)
fused[sus >= THRESH_HIGH] = 3
fused[(transit_mask==1) & (fused==0)] = 2
fused[(deposition_mask==1) & (fused==0)] = 1

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
