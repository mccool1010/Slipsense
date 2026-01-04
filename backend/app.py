from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from tiles import router as tiles_router
from pixel import router as pixel_router
import os
import urllib.request
import urllib.parse
import json
try:
    # Prefer loading a local .env file if present for development convenience
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except Exception:
    pass

app = FastAPI(title="SlipSense Tile Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tiles_router)
app.include_router(pixel_router)

# Serve static files (rasters, GeoJSON, etc.)
rasters_dir = Path(__file__).parent / "rasters"
app.mount("/rasters", StaticFiles(directory=str(rasters_dir)), name="rasters")

# Serve Cesium terrain tiles (expects a `terrain_tiles/` folder next to this file)
terrain_dir = Path(__file__).parent / "terrain_tiles"
app.mount("/terrain", StaticFiles(directory=str(terrain_dir)), name="terrain")

@app.get("/")
def root():
    return {"status": "SlipSense Tile Server running"}


@app.get("/weather")
def weather(lat: float, lon: float):
    """Proxy endpoint for OpenWeatherMap API to avoid exposing the API key in the frontend.

    Reads the API key from the `OPENWEATHER_API_KEY` environment variable.
    """
    api_key = os.environ.get("OPENWEATHER_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OpenWeather API key not configured on server")

    params = {
        "lat": lat,
        "lon": lon,
        "units": "metric",
        "appid": api_key,
    }
    url = "https://api.openweathermap.org/data/2.5/weather?" + urllib.parse.urlencode(params)

    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            return data
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8") if hasattr(e, 'read') else str(e)
        raise HTTPException(status_code=502, detail=f"OpenWeather upstream error: {detail}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

