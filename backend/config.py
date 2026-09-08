from pathlib import Path

BASE_DIR = Path(__file__).parent

# Point to the existing rasters directory. Adjust filenames if necessary.
RASTERS = {
    # v2 stack: rebuilt from a clean Copernicus GLO-30 DEM by
    # ml_models/build_terrain_stack.py, then predicted by generate_susceptibility_v2.py.
    # The pre-v2 maps rated real landslide sites at percentile 35 of their own
    # distribution - i.e. safer than average terrain - because the model was fed
    # DEM_filled_75.tif ("elevation", actually slope in degrees) and slope75.tif
    # (computed in EPSG:4326, pinned at 83-90 degrees). The v2 map puts the same
    # landslides at percentile 99.1. Originals kept alongside for comparison.
    "susceptibility_ml": BASE_DIR / "rasters" / "v2" / "susceptibility_ml.tif",
    "susceptibility_dl": BASE_DIR / "rasters" / "v2" / "susceptibility_dl.tif",
    # Conformal ambiguity mask: cells the model cannot call at alpha = 0.1.
    "uncertainty": BASE_DIR / "rasters" / "v2" / "uncertainty.tif",
    "susceptibility_ml_legacy": BASE_DIR / "rasters" / "susceptibility_ml.tif",
    "susceptibility_dl_legacy": BASE_DIR / "rasters" / "susceptibility_dl.tif",
    # Runout, rebuilt by ml_models/generate_runout_v2.py with an angle-of-reach stopping
    # criterion and multiple-flow-direction spreading. The originals were routed across
    # DEM_filled_75.tif - a slope raster treated as elevation - and their deposition rule
    # tested slope < 20 degrees against a raster that never drops below 83, so deposition
    # could never occur.
    "hazard_fused": BASE_DIR / "rasters" / "v2" / "hazard_fused.tif",
    "transit": BASE_DIR / "rasters" / "v2" / "transit_mask.tif",
    "deposition": BASE_DIR / "rasters" / "v2" / "deposition_mask.tif",
    "runout_velocity": BASE_DIR / "rasters" / "v2" / "runout_velocity.tif",
    "hazard_fused_legacy": BASE_DIR / "rasters" / "hazard_fused.tif",
    "historical_susceptibility": BASE_DIR / "rasters" / "susceptibility_historical_gsi.tif",
    "soil_susceptibility": BASE_DIR / "rasters" / "soil_susceptibility_index.tif",
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

