from pathlib import Path

BASE_DIR = Path(__file__).parent

# Point to the existing rasters directory. Adjust filenames if necessary.
RASTERS = {
    "susceptibility_ml": BASE_DIR / "rasters" / "susceptibility_ml.tif",
    "susceptibility_dl": BASE_DIR / "rasters" / "susceptibility_dl.tif",
    "hazard_fused": BASE_DIR / "rasters" / "hazard_fused.tif",
    "transit": BASE_DIR / "rasters" / "transit_mask.tif",
    "deposition": BASE_DIR / "rasters" / "deposition_mask.tif",
    "historical_susceptibility": BASE_DIR / "rasters" / "susceptibility_historical_gsi.tif",
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

