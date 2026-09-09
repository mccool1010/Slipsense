"""
features.py
The canonical feature set, in one place.

Every script that trains, predicts or evaluates has to agree on this list and its order.
They were previously each carrying their own copy, which is exactly how a model ends up
scoring one thing and a map painting another.

Selection is empirical, from `augmented_report.md`:

    terrain only (12)         AUC 0.881   PR-AUC 0.526
    terrain + soil (15)       AUC 0.883   PR-AUC 0.533
    terrain + land cover (14) AUC 0.893   PR-AUC 0.624   <- land cover does the work
    terrain + road (13)       AUC 0.883   PR-AUC 0.505
    everything (18)           AUC 0.896   PR-AUC 0.625

Land cover is what mattered: PR-AUC rises 19% when it is added, and `forest_fraction`
outranks every terrain variable by permutation importance (+0.195 against +0.166 for
relative relief). That is signal a DEM cannot contain - two identical hillsides, one
forested and one cleared, are indistinguishable to terrain alone.

`dist_road` is deliberately excluded. It contributes essentially nothing beyond land
cover, and building it costs an Overpass crawl per tile (~45 minutes each). It stays in
the dataset as a bias diagnostic, not as a predictor.
"""

# Terrain, from the DEM.
TERRAIN = [
    "elevation", "slope", "plan_curvature", "profile_curvature",
    "twi", "spi", "flow_acc", "dist_river", "drainage_density",
    "relative_relief", "aspect_north", "aspect_east",
]

# Vegetation, from ESA WorldCover.
LANDCOVER = ["forest_fraction", "bare_fraction"]

# Soil, from SoilGrids 250 m.
SOIL = ["soil_clay", "soil_sand", "soil_index"]

# What the deployed model uses.
DEPLOYED = TERRAIN + LANDCOVER + SOIL

# Kept in the dataset for the inventory-bias probe, not used for prediction.
DIAGNOSTIC = ["dist_road"]

# Rasters that back each feature. aspect_north/aspect_east are derived from aspect.tif
# at sample time, so they have no layer of their own.
DERIVED_FROM_ASPECT = {"aspect_north", "aspect_east"}


def raster_layers(features=None):
    """Layer names needed to evaluate the given features."""
    feats = DEPLOYED if features is None else features
    return [f for f in feats if f not in DERIVED_FROM_ASPECT]
