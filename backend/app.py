from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from config import BASE_DIR, RASTER_DIR, RASTERS
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

# Static files: the vector products the frontend fetches directly, chiefly
# /rasters/v2/runout_paths_exposed.geojson.
#
# The directory differs between layouts. In development RASTER_DIR is
# backend/rasters/v2, so the mount has to be its parent for that URL to resolve; in the
# deployment bundle RASTER_DIR is deploy/rasters and already contains v2/. Rather than
# encode either assumption, mount whichever candidate actually holds a v2 directory.
def _static_root():
    for candidate in (RASTER_DIR, RASTER_DIR.parent, BASE_DIR / "rasters"):
        if (candidate / "v2").is_dir():
            return candidate
    fallback = BASE_DIR / "rasters"
    return fallback if fallback.is_dir() else None


_static = _static_root()
if _static is not None:
    app.mount("/rasters", StaticFiles(directory=str(_static)), name="rasters")
else:
    print("WARNING: no raster static directory found; /rasters is unavailable.")

# Cesium terrain tiles. Optional, and absent from the deployment image on purpose: these
# are 256x256 8-bit greyscale PNGs capped at zoom 4, while Cesium's heightmap-1.0 format
# expects 65x65 16-bit binary .terrain files, so they never worked. CesiumView now reads
# open terrarium elevation tiles instead.
#
# StaticFiles raises if the directory is missing, which took down the entire server on
# first deploy - an optional, unused asset directory must not be able to do that.
terrain_dir = BASE_DIR / "terrain_tiles"
if terrain_dir.is_dir():
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
    # The *_legacy layers are the superseded rasters, kept locally so the before/after
    # comparison figure can be regenerated. They are deliberately excluded from the
    # deployment image, so requiring them would make every container report unhealthy -
    # and the healthcheck would fail the deploy for a reason that has nothing to do with
    # whether the service works.
    absent = [n for n, ok in layers.items() if not ok and not n.endswith("_legacy")]
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
