from fastapi import APIRouter, HTTPException, Response
from config import RASTERS, DISTRICT_RASTERS
from rio_tiler.io import COGReader
import numpy as np
from io import BytesIO
from PIL import Image

router = APIRouter()


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


def colorize_hazard(arr):
    """
    Colorize hazard_fused raster values.
    
    arr: 2D numpy array with values 0–3
    Returns: RGB image (h, w, 3) as uint8
    
    Mapping:
    0 = Safe (transparent/black)
    1 = Deposition (Yellow)
    2 = Transit (Orange)
    3 = Failure (Red)
    """
    h, w = arr.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)

    # Deposition → Yellow
    rgb[arr == 1] = [255, 255, 0]

    # Transit → Orange
    rgb[arr == 2] = [255, 165, 0]

    # Failure → Red
    rgb[arr == 3] = [220, 38, 38]

    return rgb


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
                img = Image.fromarray(img_arr, mode="RGB")
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

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
