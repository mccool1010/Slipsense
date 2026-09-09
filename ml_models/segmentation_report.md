# Segmentation Overlap (IoU / Dice)

Susceptibility thresholded at each calibrated tier, compared with 42 Sentinel-2 scars represented as equal-area circles (median radius 22 m), evaluated in 300 m windows.

| Tier | Threshold | IoU | Dice | Recall | Precision | Scars |
|---|---|---|---|---|---|---|
| WATCH | 0.374 | 0.018 | 0.035 | 0.348 | 0.019 | 42 |
| HIGH | 0.619 | 0.008 | 0.016 | 0.030 | 0.011 | 42 |
| VERY HIGH | 0.869 | 0.013 | 0.026 | 0.017 | 0.061 | 42 |

Best Dice: **0.035** at the WATCH tier (recall 0.348).

## How to read this

These are the metrics originally asked of this project, and they could
not be produced honestly before now: the old U-Net was an autoencoder
with no segmentation target, and a 279-point inventory has no extent to
overlap with. Satellite-mapped scars have real shape, so the question
finally means something.

**Susceptibility is not segmentation.** The map answers whether a slope
*could* fail, not whether it *did* during one observation window. Terrain
that is genuinely dangerous but did not fail counts here as a false
positive, which bounds IoU well below what a true segmentation model
would reach. Recall is the more meaningful half of this table.

**The scars are unverified candidates** - NDVI loss on steep ground is
also caused by logging, quarrying and seasonal agriculture. Treat this as
indicative, not as a benchmark result.

## The honest reading: this is the wrong metric for this product

IoU of 0.008-0.035 looks damning, and it is not. The measurement is mismatched to what
is being measured, in three compounding ways.

**The scars are smaller than the model's pixels.** Median equal-area radius is 22 m
against a 30 m grid, so a typical scar is one or two cells. IoU asks whether the flagged
region coincides *cell for cell* with something roughly the size of one cell. At this
resolution that is close to asking for a coin flip to land on its edge.

**Susceptibility is not segmentation.** The map answers "could this slope fail". A scar
is "this slope did fail, once, in the window between two satellite passes". Every
genuinely dangerous slope that simply did not fail in 2024 is scored here as a false
positive. Precision is therefore bounded by the event rate, not by model quality, and
IoU inherits that bound directly.

**Shape is unavailable.** `sentinel_scars.geojson` stores centroids and areas, not
polygons, so each scar is approximated by an equal-area circle. Real debris tracks are
long and thin; the Wayanad feature is a linear track several hundred metres long.
Comparing a circle against a ribbon loses overlap even where the model is right.

**Recall is the interpretable half of this table**: at the WATCH tier the map covers
**34.8%** of mapped scar area while flagging 5% of terrain. Read alongside the
percentile evidence in `sentinel_validation_report.md` - scars land in the map's top
quintile at 3.7x chance, p = 2e-13 - the picture is consistent: the surface ranks
dangerous ground well, and does not delineate individual scars. It was never built to.

**What would make IoU meaningful.** A true segmentation model, trained on polygon scar
masks at 10 m rather than on point labels at 30 m, predicting *extent* rather than
*propensity*. The scar masks needed for that are computed inside
`sentinel_inventory.py` and currently discarded at the centroid step; exporting them is
the prerequisite, and the natural next step if this metric matters for the writeup.
