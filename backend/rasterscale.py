"""
rasterscale.py
Convert quantised raster values back to physical units.

The deployment bundle stores bounded layers - susceptibility probabilities, the
uncertainty flag, the soil index - as uint8 rather than float32. That is a 4x saving on
data nobody reads past three decimal places, and it takes the served bundle from 181 MB
to 32 MB, which is the difference between an awkward deployment and an easy one.

The cost is that a reader must undo it. A susceptibility of 0.891 is stored as pixel
227, and 227 compared against a 0.869 threshold classifies as VERY HIGH for entirely the
wrong reason - every pixel would. So every consumer has to convert, and the conversion
has to live in one place: the tile colouriser and the pixel endpoint disagreeing about
units would be invisible until someone checked a number by hand.

The transform is recorded in the file's own tags by ml_models/build_deploy_bundle.py, so
scaled and unscaled rasters can be mixed freely - development runs against the float32
originals, production against the bundle, and neither needs to know which it has.
"""

import numpy as np


def scale_offset(src):
    """The (scale, offset) recorded on a raster, or (None, None) if it is unquantised."""
    tags = src.tags()
    if "SCALE" not in tags:
        return None, None
    try:
        return float(tags["SCALE"]), float(tags.get("OFFSET", 0.0))
    except (TypeError, ValueError):
        return None, None


def to_physical(src, arr):
    """Return `arr` in physical units, converting only if the raster is quantised.

    Quantised files reserve 0 for nodata and map the value range onto 1..255, so the
    inverse is `offset + (pixel - 1) * scale`, with 0 becoming NaN.
    """
    scale, offset = scale_offset(src)
    if scale is None:
        return arr

    out = np.asarray(arr, dtype=np.float32)
    valid = out > 0
    result = np.full(out.shape, np.nan, dtype=np.float32)
    result[valid] = offset + (out[valid] - 1.0) * scale
    return result


def is_quantised(src):
    return scale_offset(src)[0] is not None
