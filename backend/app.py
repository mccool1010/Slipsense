from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from config import RASTERS
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

# Alert system router. Loaded defensively: alerting pulls in shapely and the SMS
# providers, and none of that is needed to serve tiles or pixel queries. A missing
# optional dependency should disable one feature, not the entire server.
ALERTS_ENABLED = False
try:
    from alerts import router as alerts_router
    app.include_router(alerts_router)
    ALERTS_ENABLED = True
except Exception as exc:  # pragma: no cover - depends on the local environment
    print(f"WARNING: alert system unavailable ({exc}). "
          f"Tiles and pixel queries still work. "
          f"Install backend/requirements.txt to enable alerts.")

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



@app.get("/health")
def health():
    """One request that says which subsystems are actually up.

    Diagnosing this project previously meant reading a uvicorn traceback: a single
    missing package in the active virtualenv (shapely, then requests) stopped the whole
    server, and from the browser that was indistinguishable from broken layers, broken
    hover and a broken map. This reports the state directly.
    """
    import importlib

    deps = {}
    for mod, needed_for in (
        ("fastapi", "server"), ("rio_tiler", "tiles"), ("rasterio", "rasters"),
        ("PIL", "tile rendering"), ("requests", "pixel info, weather"),
        ("shapely", "district alerts"), ("twilio", "SMS delivery"),
    ):
        try:
            importlib.import_module(mod)
            deps[mod] = {"ok": True, "needed_for": needed_for}
        except Exception as exc:
            deps[mod] = {"ok": False, "needed_for": needed_for, "error": str(exc)}

    layers = {}
    for name, path in RASTERS.items():
        layers[name] = Path(path).exists()

    missing = [m for m, v in deps.items() if not v["ok"]]
    absent = [n for n, ok in layers.items() if not ok]
    return {
        "ok": not missing and not absent,
        "dependencies": deps,
        "layers_present": layers,
        "alerts_enabled": ALERTS_ENABLED,
        "hint": (
            f"Install missing packages into the running interpreter: "
            f"python -m pip install -r backend/requirements.txt  (missing: {missing})"
            if missing else
            f"Rebuild missing rasters with ml_models/build_terrain_stack.py "
            f"(absent: {absent})" if absent else "All subsystems available."
        ),
    }
