"""
physics_fos.py
Infinite-slope factor of safety with rainfall-driven pore pressure.

The machine-learned map is a statistical statement: these slopes resemble ones that have
failed. This is a mechanical one: on this slope, with this soil and this much water in
it, do the driving forces exceed the resisting forces? The two are independent lines of
evidence. Where they agree, confidence is high; where they diverge is where the
interesting ground is - and given that the baseline comparison showed the ML failing to
beat relative relief out of sample, having a second, non-statistical opinion matters.

The infinite-slope model is the standard for shallow translational failures, which is
what the Western Ghats produce: a soil mantle a metre or two deep sliding on weathered
bedrock, with a failure plane long relative to its depth.

    FS = [c' + (gamma*z - gamma_w*h_w) * cos^2(beta) * tan(phi')]
         / [gamma * z * sin(beta) * cos(beta)]

FS > 1 is stable, FS < 1 unstable. Rainfall enters through h_w, the height of the
saturated wedge above the failure plane: wetting raises pore pressure, cancels part of
the normal stress, and removes frictional resistance.

Wetness is distributed with the topographic wetness index rather than assumed uniform,
because convergent hollows saturate first and fail first.

Parameter values are literature defaults for weathered lateritic soils over gneiss,
which is the dominant Western Ghats profile. They are not calibrated against measured
soil properties for this catchment - none exist in the repository - so the output should
be read as a relative index and a cross-check, not as a site-specific safety assessment.

Run:  python ml_models/physics_fos.py [--rain-mm 200]
"""

import argparse
import time
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "backend" / "rasters" / "v2"

# Weathered lateritic soil over gneiss - typical Western Ghats regolith.
COHESION_KPA = 5.0          # c'  effective cohesion, incl. modest root reinforcement
FRICTION_DEG = 32.0         # phi' effective friction angle
UNIT_WEIGHT = 18.0          # gamma, kN/m3, moist soil
WATER_UNIT_WEIGHT = 9.81    # gamma_w, kN/m3
SOIL_DEPTH_M = 1.5          # z, typical mantle thickness on Ghats hillslopes
POROSITY = 0.35             # drainable porosity, for converting rain depth to head


def log(msg, t0=None):
    print(f"{msg}{f'  [{time.time() - t0:6.1f}s]' if t0 else ''}", flush=True)


def read(name):
    with rasterio.open(V2 / f"{name}.tif") as src:
        a = src.read(1).astype(np.float64)
        return a, src.profile.copy()


def saturation_from_rain(twi, rain_mm, depth_m=SOIL_DEPTH_M, porosity=POROSITY):
    """Height of the saturated wedge, in metres, from rainfall and wetness index.

    Rain is redistributed by TWI: a cell twice as topographically wet as the median
    receives proportionally more of the infiltrating water. The wedge cannot exceed the
    soil depth - beyond that the profile is fully saturated and further rain runs off.
    """
    finite = np.isfinite(twi)
    med = np.nanmedian(twi[finite]) if finite.any() else 1.0
    weight = np.where(finite, np.clip(twi / max(med, 1e-6), 0.2, 3.0), 1.0)
    head = (rain_mm / 1000.0) * weight / max(porosity, 1e-6)
    return np.clip(head, 0.0, depth_m)


def factor_of_safety(slope_deg, h_w, depth_m=SOIL_DEPTH_M):
    """Infinite-slope factor of safety."""
    beta = np.radians(np.clip(slope_deg, 0.5, 89.0))
    phi = np.radians(FRICTION_DEG)

    normal = (UNIT_WEIGHT * depth_m - WATER_UNIT_WEIGHT * h_w) * np.cos(beta) ** 2
    # Suction is not modelled, so effective normal stress cannot go negative.
    resisting = COHESION_KPA + np.maximum(normal, 0.0) * np.tan(phi)
    driving = UNIT_WEIGHT * depth_m * np.sin(beta) * np.cos(beta)

    with np.errstate(divide="ignore", invalid="ignore"):
        fs = resisting / driving
    # Flat ground has no driving stress at all; report it as strongly stable rather
    # than as a division blow-up.
    return np.where(driving > 1e-6, fs, 10.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rain-mm", type=float, default=200.0,
                    help="rainfall event depth driving pore pressure")
    ap.add_argument("--depth", type=float, default=SOIL_DEPTH_M)
    args = ap.parse_args()
    t0 = time.time()

    slope, profile = read("slope")
    twi, _ = read("twi")
    nodata = ~np.isfinite(slope)

    log(f"Computing factor of safety for a {args.rain_mm:.0f} mm event "
        f"on {args.depth:.1f} m soil ...")
    h_w = saturation_from_rain(twi, args.rain_mm, args.depth)
    fs = factor_of_safety(slope, h_w, args.depth)
    fs = np.where(nodata, np.nan, fs)

    # Dry-state comparison isolates how much of the instability rainfall is responsible
    # for, rather than how much is simply steep ground.
    fs_dry = np.where(nodata, np.nan, factor_of_safety(slope, np.zeros_like(slope),
                                                       args.depth))

    finite = fs[np.isfinite(fs)]
    unstable = float((finite < 1.0).mean() * 100)
    marginal = float(((finite >= 1.0) & (finite < 1.3)).mean() * 100)
    dry_unstable = float((fs_dry[np.isfinite(fs_dry)] < 1.0).mean() * 100)

    log(f"  FS median {np.median(finite):.2f}")
    log(f"  unstable (FS < 1.0)      {unstable:5.2f}% of terrain "
        f"(dry: {dry_unstable:.2f}%)")
    log(f"  marginal (1.0 <= FS < 1.3) {marginal:5.2f}%")
    log(f"  rainfall accounts for {unstable - dry_unstable:.2f} percentage points")

    out_profile = profile.copy()
    out_profile.update(dtype="float32", count=1, nodata=np.nan, compress="lzw")
    for name, arr in (("factor_of_safety", fs), ("factor_of_safety_dry", fs_dry),
                      ("saturated_head", np.where(nodata, np.nan, h_w))):
        with rasterio.open(V2 / f"{name}.tif", "w", **out_profile) as dst:
            dst.write(arr.astype(np.float32), 1)
        log(f"  wrote {name}.tif")

    # Agreement with the statistical model: two independent routes to the same call.
    sus_path = V2 / "susceptibility_ml.tif"
    if sus_path.exists():
        with rasterio.open(sus_path) as src:
            sus = src.read(1).astype(np.float64)
        both = np.isfinite(sus) & np.isfinite(fs)
        ml_high = sus >= 0.704
        phys_unstable = fs < 1.0
        agree_hazard = float((ml_high & phys_unstable & both).sum())
        ml_only = float((ml_high & ~phys_unstable & both).sum())
        phys_only = float((~ml_high & phys_unstable & both).sum())
        log("\nAgreement with the ML map:")
        log(f"  both flag hazard      {agree_hazard:12,.0f} cells")
        log(f"  ML only               {ml_only:12,.0f} cells")
        log(f"  physics only          {phys_only:12,.0f} cells")
        if ml_high[both].sum():
            log(f"  of ML-flagged cells, {100 * agree_hazard / ml_high[both].sum():.1f}% "
                f"are also mechanically unstable")
    log("Done.", t0)


if __name__ == "__main__":
    main()
