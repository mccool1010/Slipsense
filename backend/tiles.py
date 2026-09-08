from fastapi import APIRouter, HTTPException, Response
from config import RASTERS, DISTRICT_RASTERS
from rio_tiler.io import COGReader
from rio_tiler.errors import TileOutsideBounds
import numpy as np
from io import BytesIO
from PIL import Image

router = APIRouter()


def _make_empty_tile():
    """A single fully transparent 256x256 PNG, encoded once at import."""
    buf = BytesIO()
    Image.new("RGBA", (256, 256), (0, 0, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


_EMPTY_TILE = _make_empty_tile()


def _normalize_band(band):
    mn = float(np.nanmin(band))
    mx = float(np.nanmax(band))
    if mx - mn == 0:
        return np.zeros_like(band)
    out = (band - mn) / (mx - mn) * 255.0
    return np.clip(out, 0, 255)


def _normalize_rgb(arr):
    # arr shape (h,w,bands)
    bands = []
    for i in range(arr.shape[2]):
        bands.append(_normalize_band(arr[:, :, i]))
    stacked = np.stack(bands, axis=2)
    return stacked


# Susceptibility class breaks, imported from the alert module rather than restated
# here. They are recalibrated by ml_models/calibrate_alert_threshold.py every time the
# map is regenerated, and a second hardcoded copy had already fallen out of step - the
# map would have been drawn with the previous model's cutoffs while alerts used the
# current ones.
from alerts import (SUSCEPTIBILITY_WATCH, SUSCEPTIBILITY_HIGH,
                    SUSCEPTIBILITY_VERY_HIGH)

SUSCEPTIBILITY_BREAKS = (SUSCEPTIBILITY_WATCH, SUSCEPTIBILITY_HIGH,
                         SUSCEPTIBILITY_VERY_HIGH)


def colorize_susceptibility(band):
    """Colour a susceptibility probability raster with absolute class breaks.

    Continuous layers were previously rendered with _normalize_band, which rescales
    each tile to its own min and max. That makes the colours mean something different
    in every tile - a quiet lowland tile is stretched to look as dangerous as a tile
    full of failure zones - and it hides the real distribution, which is heavily skewed
    toward zero. Fixed breaks keep one colour meaning one probability everywhere, and
    keep the map consistent with the alert tiers.
    """
    h, w = band.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    low, high, very_high = SUSCEPTIBILITY_BREAKS

    valid = np.isfinite(band)
    # Below WATCH: faint, so safe ground recedes instead of competing for attention.
    sel = valid & (band < low)
    rgba[sel] = [30, 64, 120, 60]
    sel = valid & (band >= low) & (band < high)
    rgba[sel] = [250, 204, 21, 170]        # WATCH - amber
    sel = valid & (band >= high) & (band < very_high)
    rgba[sel] = [249, 115, 22, 200]        # HIGH - orange
    sel = valid & (band >= very_high)
    rgba[sel] = [220, 38, 38, 230]         # VERY HIGH - red
    return rgba


def colorize_uncertainty(band):
    """Hatch-free shading for cells the model cannot call.

    `uncertainty.tif` marks cells whose conformal prediction set contains both labels
    at alpha = 0.1 - about a quarter of the grid. Showing them distinctly is more
    honest than painting a single confident-looking number everywhere, and it matters
    most on the nine extrapolated tiles the model was never trained on.
    """
    h, w = band.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    ambiguous = np.isfinite(band) & (band > 0.5)
    rgba[ambiguous] = [148, 163, 184, 130]   # neutral slate, deliberately unalarming
    return rgba


def colorize_hazard(arr):
    """
    Colorize hazard_fused raster values.
    
    arr: 2D numpy array with values 0–3
    Returns: RGBA image (h, w, 4) as uint8 with transparency for safe zones
    
    Mapping:
    0 = Safe (fully transparent)
    1 = Deposition (Warm Yellow, semi-transparent)
    2 = Transit (Orange, semi-transparent)
    3 = Failure (Red, more opaque)
    """
    h, w = arr.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)

    # Deposition → Warm Yellow (semi-transparent)
    rgba[arr == 1] = [255, 220, 50, 200]

    # Transit → Orange (semi-transparent)
    rgba[arr == 2] = [255, 140, 0, 200]

    # Failure → Red (more opaque)
    rgba[arr == 3] = [220, 38, 38, 220]

    # Safe (0) stays [0,0,0,0] → fully transparent
    return rgba


def colorize_historical_susceptibility(arr):
    """
    Colorize historical susceptibility raster values from GSI/KSDMA data.
    
    arr: 2D numpy array with values 0, 2, 3, 4 (NoData=0, Low=2, Moderate=3, High=4)
    Returns: RGBA image (h, w, 4) as uint8 with transparency for NoData
    
    Mapping (KSDMA GSI 2022 classification):
    0 = NoData (transparent)
    2 = Low (Green)
    3 = Moderate (Yellow)
    4 = High (Red)
    """
    h, w = arr.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)

    # Low → Green
    mask_low = (arr == 2)
    rgba[mask_low] = [34, 197, 94, 255]  # #22c55e - green

    # Moderate → Yellow/Orange
    mask_mod = (arr == 3)
    rgba[mask_mod] = [234, 179, 8, 255]  # #eab308 - yellow

    # High → Red
    mask_high = (arr == 4)
    rgba[mask_high] = [220, 38, 38, 255]  # #dc2626 - red

    # NoData remains transparent (alpha=0)
    # Already initialized to zeros

    return rgba


@router.get("/tiles/{layer}/{z}/{x}/{y}.png")
def tile(layer: str, z: str, x: str, y: str, district: str = None):
    if layer not in RASTERS:
        raise HTTPException(status_code=404, detail="Layer not found")

    # For historical_susceptibility, use district-specific raster if specified
    if layer == "historical_susceptibility" and district and district != "all":
        if district in DISTRICT_RASTERS:
            raster_path = str(DISTRICT_RASTERS[district])
        else:
            raise HTTPException(status_code=404, detail=f"District '{district}' not found")
    else:
        raster_path = str(RASTERS[layer])

    # Coerce tile coordinates to integers and provide a helpful error
    try:
        z_i = int(z)
        x_i = int(x)
        y_i = int(y)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tile coordinates. Use integers for {z}/{x}/{y}.")

    try:
        with COGReader(raster_path) as cog:
            data, mask = cog.tile(x_i, y_i, z_i)
            # data shape (bands, height, width)
            data = np.nan_to_num(data, nan=0)
            data = np.transpose(data, (1, 2, 0))

            if layer == "historical_susceptibility":
                # Special handling for GSI historical susceptibility with transparency
                band = data[:, :, 0].astype(np.uint8)
                img_arr = colorize_historical_susceptibility(band)
                img = Image.fromarray(img_arr, mode="RGBA")
            elif layer == "hazard_fused":
                # Special handling for hazard_fused: colorize based on values 0-3
                band = data[:, :, 0].astype(np.uint8)
                img_arr = colorize_hazard(band)
                img = Image.fromarray(img_arr, mode="RGBA")
            elif layer in ("susceptibility_ml", "susceptibility_dl"):
                # Absolute class breaks, not per-tile normalisation - see
                # colorize_susceptibility for why that distinction matters.
                band = data[:, :, 0].astype(float)
                img_arr = colorize_susceptibility(band)
                # nan_to_num above turned nodata into 0, which would otherwise paint as
                # "safe"; the tile mask is what actually distinguishes the two.
                img_arr[mask == 0] = [0, 0, 0, 0]
                img = Image.fromarray(img_arr, mode="RGBA")
            elif layer == "uncertainty":
                band = data[:, :, 0].astype(float)
                img_arr = colorize_uncertainty(band)
                img_arr[mask == 0] = [0, 0, 0, 0]
                img = Image.fromarray(img_arr, mode="RGBA")
            elif data.shape[2] == 1:
                band = data[:, :, 0]
                img_arr = _normalize_band(band).astype('uint8')
                img = Image.fromarray(img_arr, mode='L')
            else:
                img_arr = _normalize_rgb(data).astype('uint8')
                # If more than 3 bands, pick first 3
                if img_arr.shape[2] > 3:
                    img_arr = img_arr[:, :, :3]
                img = Image.fromarray(img_arr, mode='RGB')

            buf = BytesIO()
            img.save(buf, format='PNG')
            return Response(content=buf.getvalue(), media_type='image/png')

    except TileOutsideBounds:
        # A web map requests a full grid of tiles across the viewport, but each raster
        # covers only its own footprint - the v2 stack is a single 1x1 degree tile. Every
        # request outside it previously returned HTTP 500, so Leaflet drew nothing at all
        # and the layer looked broken even where data existed. Serving a transparent tile
        # is what a tile server is supposed to do here.
        return Response(content=_EMPTY_TILE, media_type="image/png")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/layers/bounds")
def layer_bounds():
    """WGS84 bounds and zoom hint for every configured raster layer.

    The v2 stack covers a single 1x1 degree tile, which is a small fraction of the
    Kerala view the app opens on. With no way to discover that, a correctly working
    layer is indistinguishable from a broken one: everything outside the footprint is
    legitimately transparent, so the map just looks empty. The frontend uses this to
    fit the view to real coverage and to outline it.
    """
    from rasterio.warp import transform_bounds

    out = {}
    for name, path in RASTERS.items():
        try:
            with COGReader(str(path)) as cog:
                src = cog.dataset
                west, south, east, north = transform_bounds(
                    src.crs, "EPSG:4326", *src.bounds, densify_pts=21)
            out[name] = {
                # Leaflet order: [[south, west], [north, east]]
                "bounds": [[round(south, 6), round(west, 6)],
                           [round(north, 6), round(east, 6)]],
                "area_deg2": round(abs((east - west) * (north - south)), 4),
            }
        except Exception as exc:  # a missing or unreadable layer must not break the rest
            out[name] = {"error": str(exc)}
    return out
