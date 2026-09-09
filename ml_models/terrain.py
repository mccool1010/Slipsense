"""
terrain.py
Derive a correct terrain feature stack from a clean DEM.

The shipped rasters could not be used:
  - backend/rasters/DEM_filled_75.tif holds slope in degrees, not elevation
  - backend/rasters/slope75.tif was computed in EPSG:4326, so horizontal units are
    degrees while vertical units are metres; every cell reads 83-90 degrees
  - Distance_to_River_75.tif contains only 0 and 1 (a mask, not a distance surface)
  - SCA75.tif is entirely nodata; curvature75.sdat is a 3-class uint8, not curvature

Everything here is computed on a DEM reprojected to EPSG:32643 (UTM 43N, metres), so
horizontal and vertical units match and the derivatives are physically meaningful.

Algorithms
  fill_depressions  Priority-Flood (Barnes, Lehman & Mulla 2014)
  slope / aspect    Horn (1981), the same 3x3 kernel ArcGIS and GDAL use
  curvature         Zevenbergen & Thorne (1987), plan and profile components
  flow accumulation D8 steepest descent, accumulated in descending-elevation order
  TWI / SPI         ln(a / tan(beta)) and a * tan(beta) on specific catchment area
"""

import heapq
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, calculate_default_transform, reproject
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
TARGET_CRS = "EPSG:32643"
TARGET_RES = 30.0

# D8 neighbour offsets, clockwise from east, with their centre-to-centre distances.
D8 = [(0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1)]
D8_DIST = np.array([1.0, np.sqrt(2), 1.0, np.sqrt(2), 1.0, np.sqrt(2), 1.0, np.sqrt(2)])


def reproject_dem(src_path, dst_path, dst_crs=TARGET_CRS, res=TARGET_RES):
    """Reproject a DEM to a metric CRS so slope and curvature are physically valid."""
    with rasterio.open(src_path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds, resolution=res
        )
        profile = src.profile.copy()
        profile.update(crs=dst_crs, transform=transform, width=width, height=height,
                       dtype="float32", count=1, nodata=np.nan, compress="lzw")
        with rasterio.open(dst_path, "w", **profile) as dst:
            reproject(
                source=rasterio.band(src, 1),
                destination=rasterio.band(dst, 1),
                src_transform=src.transform, src_crs=src.crs,
                dst_transform=transform, dst_crs=dst_crs,
                resampling=Resampling.bilinear,
                src_nodata=src.nodata, dst_nodata=np.nan,
            )
    return dst_path


def fill_depressions(dem, nodata_mask, epsilon=1e-4):
    """Priority-Flood depression filling, epsilon variant (Barnes et al. 2014).

    Cells are raised to the lowest elevation reachable from the grid edge, so every
    cell drains outward. Without this, D8 accumulation terminates in spurious pits and
    TWI is undefined across large parts of the grid.

    Each filled cell is raised a hair *above* its spill point rather than exactly to it.
    Filling to the spill elevation leaves the former depression perfectly flat, and a
    steepest-descent rule finds no downhill neighbour on a flat, so flow dies there.
    The epsilon gradient guarantees every filled cell keeps a downhill path out.
    """
    h, w = dem.shape
    filled = dem.copy()
    closed = nodata_mask.copy()
    heap = []

    # Seed with the boundary: grid edges plus the rim of every nodata region.
    edge = np.zeros((h, w), dtype=bool)
    edge[0, :] = edge[-1, :] = True
    edge[:, 0] = edge[:, -1] = True
    if nodata_mask.any():
        dilated = ndimage.binary_dilation(nodata_mask, np.ones((3, 3), bool))
        edge |= dilated & ~nodata_mask

    seeds = np.argwhere(edge & ~nodata_mask)
    for r, c in seeds:
        heapq.heappush(heap, (float(filled[r, c]), int(r), int(c)))
        closed[r, c] = True

    while heap:
        elev, r, c = heapq.heappop(heap)
        for dr, dc in D8:
            nr, nc = r + dr, c + dc
            if nr < 0 or nr >= h or nc < 0 or nc >= w or closed[nr, nc]:
                continue
            closed[nr, nc] = True
            # Raising to just above the spill elevation is what removes the pit while
            # leaving a downhill path for the flow router.
            ne = filled[nr, nc]
            if ne <= elev:
                ne = elev + epsilon
                filled[nr, nc] = ne
            heapq.heappush(heap, (float(ne), nr, nc))

    return filled


def slope_aspect(dem, res=TARGET_RES):
    """Horn's 3x3 finite difference. Returns slope in degrees and aspect in degrees."""
    z = dem
    # Horn weights the cardinal neighbours double, which damps DEM noise.
    dzdx = np.zeros_like(z)
    dzdy = np.zeros_like(z)
    dzdx[1:-1, 1:-1] = (
        (z[:-2, 2:] + 2 * z[1:-1, 2:] + z[2:, 2:])
        - (z[:-2, :-2] + 2 * z[1:-1, :-2] + z[2:, :-2])
    ) / (8 * res)
    dzdy[1:-1, 1:-1] = (
        (z[2:, :-2] + 2 * z[2:, 1:-1] + z[2:, 2:])
        - (z[:-2, :-2] + 2 * z[:-2, 1:-1] + z[:-2, 2:])
    ) / (8 * res)

    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    aspect = np.degrees(np.arctan2(dzdy, -dzdx))
    aspect = np.where(aspect < 0, aspect + 360.0, aspect)
    return slope, aspect, dzdx, dzdy


def curvature(dem, res=TARGET_RES):
    """Zevenbergen & Thorne plan and profile curvature (per 100 m)."""
    z = dem
    zx = np.zeros_like(z); zy = np.zeros_like(z)
    zxx = np.zeros_like(z); zyy = np.zeros_like(z); zxy = np.zeros_like(z)

    zx[1:-1, 1:-1] = (z[1:-1, 2:] - z[1:-1, :-2]) / (2 * res)
    zy[1:-1, 1:-1] = (z[2:, 1:-1] - z[:-2, 1:-1]) / (2 * res)
    zxx[1:-1, 1:-1] = (z[1:-1, 2:] - 2 * z[1:-1, 1:-1] + z[1:-1, :-2]) / res ** 2
    zyy[1:-1, 1:-1] = (z[2:, 1:-1] - 2 * z[1:-1, 1:-1] + z[:-2, 1:-1]) / res ** 2
    zxy[1:-1, 1:-1] = (z[2:, 2:] - z[2:, :-2] - z[:-2, 2:] + z[:-2, :-2]) / (4 * res ** 2)

    p = zx ** 2 + zy ** 2
    q = p + 1.0
    with np.errstate(invalid="ignore", divide="ignore"):
        # Plan curvature: convergence across the slope, which concentrates flow.
        plan = -(zxx * zy ** 2 - 2 * zxy * zx * zy + zyy * zx ** 2) / np.power(p, 1.5)
        # Profile curvature: change in slope downhill, which drives acceleration.
        prof = -(zxx * zx ** 2 + 2 * zxy * zx * zy + zyy * zy ** 2) / (p * np.power(q, 1.5))
    plan = np.nan_to_num(plan, nan=0.0, posinf=0.0, neginf=0.0) * 100.0
    prof = np.nan_to_num(prof, nan=0.0, posinf=0.0, neginf=0.0) * 100.0

    # Both forms divide by the gradient magnitude, so they explode toward infinity on
    # near-flat ground where that magnitude approaches zero. Curvature has no meaning
    # on a flat anyway, so zero it there and clip the rest to a physical range.
    flat = p < (np.tan(np.radians(0.5)) ** 2)
    plan[flat] = 0.0
    prof[flat] = 0.0
    return np.clip(plan, -100.0, 100.0), np.clip(prof, -100.0, 100.0)


def streams_from_accumulation(acc, nodata_mask, threshold_cells=100):
    """Define the channel network as cells draining more than `threshold_cells`.

    Preferred over the shipped River_Vectors.shp, which is a vectorisation of the old
    (broken) hydrology, so it would import those errors back into the new stack.
    100 cells at 30 m is ~9 ha, the usual first-order channel initiation threshold.
    """
    return np.isfinite(acc) & ~nodata_mask & (acc >= threshold_cells)


def flow_accumulation(filled, nodata_mask, res=TARGET_RES):
    """D8 flow accumulation, in cell counts.

    Each cell drains to its steepest downslope neighbour. Processing cells in
    descending elevation order guarantees every upstream contributor is accumulated
    before the cell that receives it, so one pass is exact.
    """
    h, w = filled.shape
    n = h * w
    z = np.where(nodata_mask, -np.inf, filled).astype(np.float64)

    # receiver[i] = flat index this cell drains into, or -1 if it drains off-grid.
    receiver = np.full(n, -1, dtype=np.int64)
    best_drop = np.zeros(n, dtype=np.float64)

    for k, (dr, dc) in enumerate(D8):
        shifted = np.full_like(z, -np.inf)
        rs = slice(max(0, -dr), h - max(0, dr))
        cs = slice(max(0, -dc), w - max(0, dc))
        rd = slice(max(0, dr), h - max(0, -dr))
        cd = slice(max(0, dc), w - max(0, -dc))
        shifted[rs, cs] = z[rd, cd]

        drop = (z - shifted) / (D8_DIST[k] * res)
        drop = np.where(np.isfinite(drop), drop, -np.inf)

        better = (drop > best_drop.reshape(h, w)) & (drop > 0)
        if better.any():
            rr, cc = np.nonzero(better)
            flat = rr * w + cc
            best_drop[flat] = drop[rr, cc]
            receiver[flat] = (rr + dr) * w + (cc + dc)

    acc = np.ones(n, dtype=np.float64)
    acc[nodata_mask.ravel()] = 0.0

    order = np.argsort(z.ravel(), kind="stable")[::-1]
    for i in order:
        r = receiver[i]
        if r >= 0:
            acc[r] += acc[i]

    acc = acc.reshape(h, w)
    acc[nodata_mask] = np.nan
    return acc


def wetness_indices(acc, slope_deg, res=TARGET_RES):
    """Topographic and stream-power indices from specific catchment area."""
    # Specific catchment area: upslope area per unit contour width.
    sca = acc * res
    beta = np.tan(np.radians(np.clip(slope_deg, 0.1, 89.9)))
    with np.errstate(invalid="ignore", divide="ignore"):
        twi = np.log(sca / beta)
        spi = np.log1p(sca * beta)   # log form; raw SPI spans 7 orders of magnitude
    return twi, spi


def rasterize_lines(lines, shape, transform):
    """Burn polyline vertices and their connecting segments into a boolean grid."""
    mask = np.zeros(shape, dtype=bool)
    inv = ~transform
    h, w = shape
    for line in lines:
        if len(line) < 2:
            continue
        cols, rows = inv * (line[:, 0], line[:, 1])
        cols = np.asarray(cols); rows = np.asarray(rows)
        # Densify each segment so no cell is skipped between distant vertices.
        for i in range(len(cols) - 1):
            steps = int(max(abs(cols[i + 1] - cols[i]), abs(rows[i + 1] - rows[i]))) + 1
            cc = np.linspace(cols[i], cols[i + 1], steps).astype(int)
            rr = np.linspace(rows[i], rows[i + 1], steps).astype(int)
            ok = (rr >= 0) & (rr < h) & (cc >= 0) & (cc < w)
            mask[rr[ok], cc[ok]] = True
    return mask


def distance_to(mask, res=TARGET_RES):
    """Euclidean distance in metres from every cell to the nearest True cell."""
    return ndimage.distance_transform_edt(~mask, sampling=res).astype(np.float32)


def density(mask, res=TARGET_RES, radius_m=1000.0):
    """Line density (km of line per km2) within a circular window."""
    r = max(1, int(round(radius_m / res)))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    kernel = (xx ** 2 + yy ** 2) <= r ** 2
    counts = ndimage.uniform_filter(mask.astype(np.float32), size=2 * r + 1) * (2 * r + 1) ** 2
    area_km2 = kernel.sum() * (res ** 2) / 1e6
    length_km = counts * res / 1000.0
    return (length_km / area_km2).astype(np.float32)


def relative_relief(dem, res=TARGET_RES, radius_m=500.0):
    """Local elevation range (max - min) within a moving window."""
    size = max(3, int(round(2 * radius_m / res)) | 1)
    hi = ndimage.maximum_filter(dem, size=size, mode="nearest")
    lo = ndimage.minimum_filter(dem, size=size, mode="nearest")
    return (hi - lo).astype(np.float32)


def write_like(path, data, profile):
    """Write a single-band float32 GeoTIFF using a reference profile."""
    p = profile.copy()
    p.update(dtype="float32", count=1, nodata=np.nan, compress="lzw")
    with rasterio.open(path, "w", **p) as dst:
        dst.write(np.asarray(data, dtype=np.float32), 1)
