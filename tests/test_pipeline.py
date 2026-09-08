"""
Regression tests for the SlipSense pipeline.

The project had no tests, and the defects that invalidated its published results were
exactly the kind tests catch: a raster whose contents did not match its name, a feature
generated from the label, coordinates passed in the wrong CRS, a physical model whose
stopping rule could never fire. Each test below pins one of those.

Run:  python -m pytest tests/ -v
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ml_models"))

V2 = ROOT / "backend" / "rasters" / "v2"
DATA = ROOT / "data" / "real_landslide_dataset.csv"

rasterio = pytest.importorskip("rasterio")
pd = pytest.importorskip("pandas")


# --------------------------------------------------------------------------
# Terrain: the layers must contain what their names claim
# --------------------------------------------------------------------------

def _band(name):
    path = V2 / f"{name}.tif"
    if not path.exists():
        pytest.skip(f"{name}.tif not built")
    with rasterio.open(path) as src:
        a = src.read(1).astype(float)
    return a[np.isfinite(a)]


@pytest.mark.parametrize("name,lo,hi", [
    ("slope", 0.0, 90.0),
    ("aspect", 0.0, 360.0),
    ("elevation", -50.0, 3000.0),
])
def test_layer_within_physical_range(name, lo, hi):
    v = _band(name)
    assert v.min() >= lo and v.max() <= hi, f"{name} outside [{lo}, {hi}]"


def test_slope_is_not_degenerate():
    """The old slope raster was pinned at 83-90 degrees because it was computed in
    EPSG:4326, where horizontal units are degrees and vertical are metres."""
    v = _band("slope")
    assert v.min() < 5.0, "no gentle terrain: slope raster is probably degenerate"
    assert np.median(v) < 30.0, f"median slope {np.median(v):.1f} deg is implausible"


def test_elevation_is_elevation_not_slope():
    """`DEM_filled_75.tif` held slope in degrees while being named as a DEM."""
    v = _band("elevation")
    assert v.max() > 500.0, (
        f"max elevation {v.max():.1f} m too low for the Western Ghats - "
        "this layer may be slope, not elevation")


def test_distance_to_river_is_continuous():
    """`Distance_to_River_75.tif` contained only 0 and 1 - a mask, not a distance."""
    v = _band("dist_river")
    assert len(np.unique(v[:100000])) > 50, "dist_river looks like a binary mask"
    assert v.max() > 100.0, "distance surface has implausibly small range"


def test_flow_accumulation_drains():
    """Without epsilon filling, flow dies in filled depressions and accumulation
    tops out orders of magnitude too low."""
    v = _band("flow_acc")          # stored as log1p(cells)
    assert np.expm1(v.max()) > 100_000, (
        "max flow accumulation too small - flow is probably dying in flat areas")


def test_curvature_is_bounded():
    """Curvature divides by gradient magnitude and explodes on flat ground."""
    for name in ("plan_curvature", "profile_curvature"):
        v = _band(name)
        assert np.abs(v).max() <= 100.0 + 1e-6, f"{name} not clipped"


# --------------------------------------------------------------------------
# Dataset: no synthetic rows, no label leakage
# --------------------------------------------------------------------------

def _dataset():
    if not DATA.exists():
        pytest.skip("real_landslide_dataset.csv not built")
    return pd.read_csv(DATA)


def test_dataset_has_no_synthetic_source_column():
    df = _dataset()
    if "source" in df.columns:
        bad = {"kerala", "global_catalog_synthetic", "synthetic_negative"}
        assert not bad & set(df["source"].unique()), "synthetic rows present"


def test_no_feature_separates_classes_perfectly():
    """The retracted dataset generated `dist_river` from the label, so a single
    threshold classified every synthetic row correctly."""
    df = _dataset()
    feats = [c for c in df.columns
             if c not in ("landslide", "x", "y", "lon", "lat", "source")]
    pos, neg = df[df.landslide == 1], df[df.landslide == 0]
    for f in feats:
        a, b = pos[f].dropna(), neg[f].dropna()
        if a.empty or b.empty:
            continue
        separated = a.min() > b.max() or a.max() < b.min()
        assert not separated, f"feature '{f}' separates the classes perfectly - leakage"


def test_positive_and_negative_counts_are_sane():
    df = _dataset()
    assert df.landslide.sum() >= 100, "too few positives"
    assert (df.landslide == 0).sum() >= df.landslide.sum(), "negatives should not be rarer"


# --------------------------------------------------------------------------
# Runout physics
# --------------------------------------------------------------------------

def test_runout_stops_on_flat_ground():
    """A flow released on a plane below the friction angle must not travel."""
    import runout
    dem = np.tile(np.linspace(100, 99, 60), (60, 1))   # ~1 m drop over 1800 m
    sources = np.zeros_like(dem, dtype=bool)
    sources[30, 5] = True
    out = runout.propagate(dem, sources, res=30.0, reach_angle_deg=22.0)
    assert out["transit"].sum() == 0, "debris travelled across near-flat ground"


def test_runout_travels_downhill_and_stops():
    """On a steep plane the flow should move, stay bounded, and respect the cap."""
    import runout
    dem = np.tile(np.linspace(1000, 0, 80), (40, 1))   # ~45 percent gradient
    sources = np.zeros_like(dem, dtype=bool)
    sources[20, 2] = True
    out = runout.propagate(dem, sources, res=30.0, reach_angle_deg=22.0)
    assert out["transit"].sum() > 0, "no runout on steep terrain"
    v = out["velocity"][np.isfinite(out["velocity"])]
    assert v.max() <= 30.0 + 1e-6, "velocity exceeded the cap"
    assert v.max() > 1.0, "velocity implausibly low on a steep slope"


def test_deposition_is_reachable():
    """The old deposition rule tested slope < 20 deg against a raster never below 83,
    so deposition could never occur."""
    import runout
    steep = np.tile(np.linspace(600, 0, 50), (40, 1))
    flat = np.zeros((40, 30))
    dem = np.hstack([steep, flat])
    sources = np.zeros_like(dem, dtype=bool)
    sources[20, 2] = True
    out = runout.propagate(dem, sources, res=30.0, reach_angle_deg=22.0)
    assert out["deposition"].sum() > 0, "debris never comes to rest"


# --------------------------------------------------------------------------
# Geometry and CRS
# --------------------------------------------------------------------------

def test_inventory_coordinates_land_inside_the_grid():
    """The retired data_preparation.py passed lon/lat into EPSG:32643 rasters, which
    lands every point out of bounds and silently yields NaN."""
    import geo_io
    shp = ROOT / "Landslides.shp"
    if not shp.exists() or not (V2 / "elevation.tif").exists():
        pytest.skip("inventory or terrain not available")
    pts = geo_io.read_points(shp)
    with rasterio.open(V2 / "elevation.tif") as src:
        left, bottom, right, top = src.bounds
    inside = ((pts[:, 0] >= left) & (pts[:, 0] <= right)
              & (pts[:, 1] >= bottom) & (pts[:, 1] <= top))
    assert inside.mean() > 0.95, (
        f"only {100 * inside.mean():.0f}% of inventory points fall inside the grid - "
        "likely a CRS mismatch")


def test_v2_layers_share_one_grid():
    """Mixed grids in the old stack meant features were sampled at inconsistent
    locations."""
    shapes = {}
    for p in sorted(V2.glob("*.tif")):
        with rasterio.open(p) as src:
            shapes.setdefault((src.height, src.width, str(src.crs)), []).append(p.name)
    if not shapes:
        pytest.skip("v2 stack not built")
    assert len(shapes) == 1, f"v2 layers disagree on grid or CRS: {shapes}"


# --------------------------------------------------------------------------
# Retired scripts must stay retired
# --------------------------------------------------------------------------

@pytest.mark.parametrize("script", ["data_preparation.py", "enhanced_model.py"])
def test_leaking_scripts_refuse_to_run(script):
    import subprocess
    path = ROOT / "ml_models" / script
    if not path.exists():
        pytest.skip(f"{script} absent")
    r = subprocess.run([sys.executable, str(path)], capture_output=True, text=True,
                       timeout=120)
    combined = (r.stdout + r.stderr).lower()
    assert "retired" in combined, f"{script} did not refuse to run"


# --------------------------------------------------------------------------
# Alert calibration
# --------------------------------------------------------------------------

def test_alert_thresholds_match_the_calibration_file():
    """Thresholds in alerts.py must track the map they were calibrated against."""
    calib = ROOT / "ml_models" / "alert_calibration.json"
    if not calib.exists():
        pytest.skip("calibration not run")
    tiers = json.loads(calib.read_text())["tiers"]
    src = (ROOT / "backend" / "alerts.py").read_text(encoding="utf-8")
    for name, const in (("WATCH", "SUSCEPTIBILITY_WATCH"),
                        ("HIGH", "SUSCEPTIBILITY_HIGH"),
                        ("VERY HIGH", "SUSCEPTIBILITY_VERY_HIGH")):
        expected = round(tiers[name]["threshold"], 3)
        assert f"{const} = {expected}" in src, (
            f"{const} does not match calibrated {expected}")


def test_rainfall_failure_is_not_reported_as_zero():
    """Returning 0.0 mm on API failure made an outage indistinguishable from dry
    weather, silencing alerts."""
    src = (ROOT / "backend" / "rainfall.py")
    if not src.exists():
        pytest.skip("rainfall module absent")
    text = src.read_text(encoding="utf-8")
    assert "class RainfallUnavailable" in text
    assert "return 0.0" not in text, "rainfall module still returns 0.0 on failure"
