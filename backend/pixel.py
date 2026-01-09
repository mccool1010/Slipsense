from fastapi import APIRouter, Query, HTTPException
import rasterio
from rasterio.warp import transform as rio_transform

import requests
from config import RASTERS

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

OPENWEATHER_API_KEY = "f4b4c6deaacfaacd2060175e4697b694"  # Inserted user API key

def rainfall_at(lat, lon):
    url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric"
    )
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()
        return data.get("rain", {}).get("1h", 0.0)
    except Exception:
        return 0.0


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
            x, y = to_raster_xy(lon, lat, src)
            row, col = src.index(x, y)
            band = src.read(1)
            if row < 0 or col < 0 or row >= band.shape[0] or col >= band.shape[1]:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"Coordinates out of raster bounds for susceptibility raster; "
                        f"raster_bounds={src.bounds}, raster_crs={src.crs}"
                    ),
                )
            sus = float(band[row, col])

        # --- Read hazard fused ---
        with rasterio.open(RASTERS["hazard_fused"]) as src:
            x, y = to_raster_xy(lon, lat, src)
            row, col = src.index(x, y)
            band = src.read(1)
            if row < 0 or col < 0 or row >= band.shape[0] or col >= band.shape[1]:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"Coordinates out of raster bounds for hazard raster; "
                        f"raster_bounds={src.bounds}, raster_crs={src.crs}"
                    ),
                )
            zone_code = int(band[row, col])

        zone = ZONE_MAP.get(zone_code, "Unknown")

        # --- Read Historical (GSI) susceptibility ---
        historical_sus = None
        historical_class = None
        try:
            with rasterio.open(RASTERS["historical_susceptibility"]) as src:
                x, y = to_raster_xy(lon, lat, src)
                row, col = src.index(x, y)
                band = src.read(1)
                if 0 <= row < band.shape[0] and 0 <= col < band.shape[1]:
                    hist_val = int(band[row, col])
                    historical_sus = hist_val if hist_val != 0 else None
                    historical_class = HISTORICAL_CLASS_MAP.get(hist_val, None)
        except Exception:
            pass  # Historical layer is optional

        # --- Rainfall ---
        rain = rainfall_at(lat, lon)

        # --- Risk calculation ---
        risk_val = sus * (1 + rain / 20)
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
            "historical_susceptibility": historical_sus,
            "historical_risk_class": historical_class,
            "rainfall": rain,
            "riskLevel": risk_level,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
