from fastapi import APIRouter, Query, HTTPException
import rasterio
from rasterio.windows import Window
from rasterio.warp import transform as rio_transform

import os
import time

import requests
from config import RASTERS
from thresholds import (SUSCEPTIBILITY_HIGH, SUSCEPTIBILITY_VERY_HIGH,
                        SUSCEPTIBILITY_WATCH)


def susceptibility_class(value):
    """Name the calibrated tier a probability falls in.

    A bare 0.891 means nothing to a reader without the calibration table in front of
    them. The tiers are what the alert system acts on, so the readout should speak the
    same language: these cutoffs flag 5%, 1% and 0.2% of terrain respectively.
    """
    if value is None:
        return None
    if value >= SUSCEPTIBILITY_VERY_HIGH:
        return "VERY HIGH"
    if value >= SUSCEPTIBILITY_HIGH:
        return "HIGH"
    if value >= SUSCEPTIBILITY_WATCH:
        return "WATCH"
    return "LOW"

def sample_one(src, lon_in, lat_in):
    """Read a single cell without decompressing the whole raster.

    `src.read(1)` pulls every cell into memory - 13.4M values, about 50 MB per v2 layer -
    to use exactly one of them. This endpoint touches four rasters per call and fires on
    every mouse move, so hovering was costing roughly 200 MB of I/O per pixel. A windowed
    read touches one block instead.

    Returns (value, row, col), with value None when the point falls outside the raster.
    """
    if src.crs is not None:
        try:
            xs, ys = rio_transform("EPSG:4326", src.crs, [lon_in], [lat_in])
            x, y = xs[0], ys[0]
        except Exception:
            x, y = lon_in, lat_in
    else:
        x, y = lon_in, lat_in

    row, col = src.index(x, y)
    if row < 0 or col < 0 or row >= src.height or col >= src.width:
        return None, row, col
    win = Window(col, row, 1, 1)
    return src.read(1, window=win)[0, 0], row, col



router = APIRouter()


ZONE_MAP = {
    0: "Safe",
    1: "Deposition",
    2: "Transit",
    3: "Failure",
}

HISTORICAL_CLASS_MAP = {
    0: None,  # NoData - outside susceptible zone
    2: "Low",
    3: "Moderate",
    4: "High",
}

# From the environment, never a literal. The same key was hardcoded here and in
# alerts.py, so it shipped in the repository twice; revoke it at
# https://home.openweathermap.org/api_keys and set OPENWEATHER_API_KEY instead.
# Absent, rainfall simply reports 0.0 and the rest of the endpoint still works.
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")

# Rainfall lookups are cached by coarse location and age. /pixel-info fires on every
# mouse move, and each call was making a live OpenWeather request with a 5 second
# timeout - which dominated hover latency completely once the raster reads were fixed.
# Weather does not vary meaningfully across ~5 km or within ten minutes, so rounding the
# key to two decimals collapses a whole hover session onto a handful of requests.
_RAIN_CACHE: dict = {}
_RAIN_TTL_SECONDS = 600


def rainfall_at(lat, lon):
    key = (round(lat, 2), round(lon, 2))
    hit = _RAIN_CACHE.get(key)
    if hit and (time.time() - hit[0]) < _RAIN_TTL_SECONDS:
        return hit[1]

    if not OPENWEATHER_API_KEY:
        return 0.0
    url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric"
    )
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        value = r.json().get("rain", {}).get("1h", 0.0)
    except Exception:
        value = 0.0
    _RAIN_CACHE[key] = (time.time(), value)
    return value


@router.get("/pixel-info")
def pixel_info(
    lat: float = Query(...),
    lon: float = Query(...),
):
    def to_raster_xy(lon_in, lat_in, src):
        if src.crs is None:
            return lon_in, lat_in
        try:
            xs, ys = rio_transform("EPSG:4326", src.crs, [lon_in], [lat_in])
            return xs[0], ys[0]
        except Exception:
            return lon_in, lat_in


    try:
        # --- Read DL susceptibility ---
        with rasterio.open(RASTERS["susceptibility_dl"]) as src:
            val, row, col = sample_one(src, lon, lat)
            if val is None:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"Coordinates out of raster bounds for susceptibility raster; "
                        f"raster_bounds={src.bounds}, raster_crs={src.crs}"
                    ),
                )
            sus = float(val)

        # --- Read hazard fused ---
        with rasterio.open(RASTERS["hazard_fused"]) as src:
            val, row, col = sample_one(src, lon, lat)
            if val is None:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"Coordinates out of raster bounds for hazard raster; "
                        f"raster_bounds={src.bounds}, raster_crs={src.crs}"
                    ),
                )
            zone_code = int(val)

        zone = ZONE_MAP.get(zone_code, "Unknown")

        # --- Read Historical (GSI) susceptibility ---
        historical_sus = None
        historical_class = None
        try:
            with rasterio.open(RASTERS["historical_susceptibility"]) as src:
                val, _, _ = sample_one(src, lon, lat)
                if val is not None:
                    hist_val = int(val)
                    historical_sus = hist_val if hist_val != 0 else None
                    historical_class = HISTORICAL_CLASS_MAP.get(hist_val, None)
        except Exception:
            pass  # Historical layer is optional

        # --- Read Soil Susceptibility (from SoilGrids clay/sand index) ---
        soil_sus = None
        try:
            with rasterio.open(RASTERS["soil_susceptibility"]) as src:
                raw, _, _ = sample_one(src, lon, lat)
                if raw is not None:
                    val = float(raw)
                    if val > 0 and val != -9999:
                        soil_sus = round(val, 3)
        except Exception:
            pass  # Soil layer is optional

        # --- Rainfall ---
        rain = rainfall_at(lat, lon)

        # --- Risk calculation (blended with historical, matching raster logic) ---
        hist_weight = 0.30
        if historical_sus is not None and historical_sus > 0:
            hist_map = {2: 0.25, 3: 0.55, 4: 1.0}
            hist_val_norm = hist_map.get(historical_sus, 0.0)
            blended_sus = sus * (1 - hist_weight) + hist_val_norm * hist_weight
        else:
            blended_sus = sus
        # Factor in soil susceptibility (amplifies risk for clay-rich soils)
        soil_factor = 1.0
        if soil_sus is not None:
            # Soil index 0-1: high value = clay-rich = more unstable when wet
            soil_factor = 1.0 + (soil_sus - 0.5) * 0.3  # range: 0.85 to 1.15
        risk_val = blended_sus * (1 + rain / 20) * soil_factor
        if risk_val > 0.7:
            risk_level = "High"
        elif risk_val > 0.4:
            risk_level = "Moderate"
        else:
            risk_level = "Low"

        return {
            "latitude": lat,
            "longitude": lon,
            "zone": zone,
            "susceptibility": round(sus, 3),
            # The calibrated tier this probability falls in, so the number is readable
            # without the calibration table to hand and matches what alerting acts on.
            "susceptibility_class": susceptibility_class(sus),
            "historical_susceptibility": historical_sus,
            "historical_risk_class": historical_class,
            "soil_susceptibility": soil_sus,
            "rainfall": rain,
            "riskLevel": risk_level,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
