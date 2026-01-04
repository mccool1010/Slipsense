from pathlib import Path

BASE_DIR = Path(__file__).parent

# Point to the existing rasters directory. Adjust filenames if necessary.
RASTERS = {
    "susceptibility_ml": BASE_DIR / "rasters" / "susceptibility_ml.tif",
    "susceptibility_dl": BASE_DIR / "rasters" / "susceptibility_dl.tif",
    "hazard_fused": BASE_DIR / "rasters" / "hazard_fused.tif",
    "transit": BASE_DIR / "rasters" / "transit_mask.tif",
    "deposition": BASE_DIR / "rasters" / "deposition_mask.tif",
}
