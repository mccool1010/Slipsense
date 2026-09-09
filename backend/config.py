import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Where the served rasters live.
#
# Development reads the full float32 stack in backend/rasters/v2/. Deployment reads the
# bundle built by ml_models/build_deploy_bundle.py: the same layers as Cloud-Optimised
# GeoTIFFs with overviews, quantised where the values allow it, which takes 181 MB down
# to 32 MB and makes low-zoom tiles cheap to serve. Readers handle both - see
# backend/rasterscale.py - so switching is a path change and nothing else.
#
#   SLIPSENSE_RASTER_DIR=../deploy/rasters
_default = BASE_DIR / "rasters" / "v2"
RASTER_DIR = Path(os.environ.get("SLIPSENSE_RASTER_DIR", _default))
if not RASTER_DIR.is_absolute():
    RASTER_DIR = (BASE_DIR / RASTER_DIR).resolve()

# The bundle flattens some names; fall back to the development layout when absent.
def _layer(*candidates):
    for name in candidates:
        p = RASTER_DIR / name
        if p.exists():
            return p
    return RASTER_DIR / candidates[0]

RASTERS = {
    # v2 stack: rebuilt from a clean Copernicus GLO-30 DEM by
    # ml_models/build_terrain_stack.py, then predicted by generate_susceptibility_v2.py.
    # The pre-v2 maps rated real landslide sites at percentile 35 of their own
    # distribution - i.e. safer than average terrain - because the model was fed
    # DEM_filled_75.tif ("elevation", actually slope in degrees) and slope75.tif
    # (computed in EPSG:4326, pinned at 83-90 degrees). The v2 map puts the same
    # landslides at percentile 99.1. Originals kept alongside for comparison.
    "susceptibility_ml": _layer("susceptibility_ml.tif"),
    "susceptibility_dl": _layer("susceptibility_dl.tif"),
    # Conformal ambiguity mask: cells the model cannot call at alpha = 0.1.
    "uncertainty": _layer("uncertainty.tif"),
    "susceptibility_ml_legacy": BASE_DIR / "rasters" / "susceptibility_ml.tif",
    "susceptibility_dl_legacy": BASE_DIR / "rasters" / "susceptibility_dl.tif",
    # Runout, rebuilt by ml_models/generate_runout_v2.py with an angle-of-reach stopping
    # criterion and multiple-flow-direction spreading. The originals were routed across
    # DEM_filled_75.tif - a slope raster treated as elevation - and their deposition rule
    # tested slope < 20 degrees against a raster that never drops below 83, so deposition
    # could never occur.
    "hazard_fused": _layer("hazard_fused.tif"),
    "transit": _layer("transit.tif", "transit_mask.tif"),
    "deposition": _layer("deposition.tif", "deposition_mask.tif"),
    "runout_velocity": _layer("runout_velocity.tif"),
    "hazard_fused_legacy": BASE_DIR / "rasters" / "hazard_fused.tif",
    "historical_susceptibility": _layer("historical_susceptibility.tif", "susceptibility_historical_gsi.tif"),
    "soil_susceptibility": _layer("soil_susceptibility.tif", "soil_susceptibility_index.tif"),
}

# Per-district historical susceptibility rasters
DISTRICT_RASTERS = {
    "thiruvananthapuram": BASE_DIR / "rasters" / "districts" / "susceptibility_thiruvananthapuram.tif",
    "kollam": BASE_DIR / "rasters" / "districts" / "susceptibility_kollam.tif",
    "pathanamthitta": BASE_DIR / "rasters" / "districts" / "susceptibility_pathanamthitta.tif",
    "kottayam": BASE_DIR / "rasters" / "districts" / "susceptibility_kottayam.tif",
    "idukki": BASE_DIR / "rasters" / "districts" / "susceptibility_idukki.tif",
    "ernakulam": BASE_DIR / "rasters" / "districts" / "susceptibility_ernakulam.tif",
    "thrissur": BASE_DIR / "rasters" / "districts" / "susceptibility_thrissur.tif",
    "palakkad": BASE_DIR / "rasters" / "districts" / "susceptibility_palakkad.tif",
    "malappuram": BASE_DIR / "rasters" / "districts" / "susceptibility_malappuram.tif",
    "kozhikode": BASE_DIR / "rasters" / "districts" / "susceptibility_kozhikode.tif",
    "wayanad": BASE_DIR / "rasters" / "districts" / "susceptibility_wayanad.tif",
    "kannur": BASE_DIR / "rasters" / "districts" / "susceptibility_kannur.tif",
    "kasaragod": BASE_DIR / "rasters" / "districts" / "susceptibility_kasaragod.tif",
}

# =============================================
# Alert System Configuration
# =============================================

# District boundaries GeoJSON
DISTRICT_GEOJSON = BASE_DIR.parent / "Kerala_District_Boundary.geojson"

# Risk thresholds for triggering alerts
SUSCEPTIBILITY_THRESHOLD = 0.75  # Average or max susceptibility
RAINFALL_THRESHOLD_MM = 50.0      # 24-hour rainfall in mm

