# SlipSense Model Card

Last updated: 2026-09-08

This card exists because the project previously published metrics that were wrong by a
wide margin, in ways nothing in the repository flagged. It records what each model is,
what it was trained on, what it has actually been shown to do, and — at least as
importantly — what it has not.

**One-line summary:** the susceptibility product is genuinely good — independent,
well-located landslide scars land in its top quintile at **3.7× chance** (p = 2e-13) —
but the *machine learning* does not beat a plain slope raster out of sample, so the
defensible claim is about the map, not about the model class.

---

## 1. Intended use

**Intended:** regional screening and decision support — ranking terrain by relative
landslide susceptibility, prioritising survey and inspection effort, and providing a
first-pass hazard layer for planning.

**Not intended:** site-specific safety assessment, engineering design, evacuation
decisions taken on model output alone, or any use where a single cell's value is treated
as a statement about an individual slope or building. This is a prototype. Final
authority rests with the Kerala State Disaster Management Authority and the Geological
Survey of India.

---

## 2. Models

| Model | File | Purpose |
|---|---|---|
| RandomForest susceptibility | `ml_models/susceptibility_model.pkl` | Per-cell landslide probability; drives the map and alerting |
| Patch CNN | `backend/rasters/cnn_context.pt` | Terrain-context susceptibility; display layer |
| Rainfall trigger | `ml_models/rainfall_trigger_model.pkl` | Probability that a given day's rainfall is a triggering day |
| Runout | `ml_models/runout.py` | Angle-of-reach + multiple-flow-direction debris propagation |
| Factor of safety | `ml_models/physics_fos.py` | Mechanical cross-check, independent of the statistics |

---

## 3. Training data

**Inventory:** 279 landslide points (`Landslides.shp`, EPSG:32643), paired with 2,500
non-landslide locations sampled at least 500 m from any mapped landslide and required to
have complete terrain data. Total 2,779 rows, **zero synthetic**.

**Terrain:** 11 layers derived from Copernicus GLO-30, reprojected to EPSG:32643 at 30 m
so horizontal and vertical units match. Priority-Flood+ε depression filling, Horn slope
and aspect, Zevenbergen–Thorne curvature, D8 flow accumulation, TWI/SPI, stream network
from flow accumulation.

**Rainfall:** 109 dated Western Ghats events from the NASA Global Landslide Catalog with
436 matched non-event days at the same locations; daily precipitation from the
Open-Meteo reanalysis archive.

### Known gap in provenance

The 279 inventory points carry **only an `id` attribute** — no date, source, mapping
method, or positional accuracy. `Non_Landslides.shp` contains exactly **one** point, so
the 156 negatives in the original project CSV have no traceable origin. This is not a
cosmetic issue: section 5 shows a pattern consistent with those points being spatially
biased, and it cannot be ruled out without knowing where they came from.

---

## 4. Evaluation

All figures are out-of-fold under **spatial-block cross-validation** (5 km blocks).
Random splits are not used for headline numbers: landslide points cluster, so a random
split puts near-identical neighbouring cells in both train and test.

| Model | AUC | PR-AUC | Precision | Recall | F1 |
|---|---|---|---|---|---|
| Patch CNN | 0.896 | 0.593 | 0.556 | 0.556 | 0.556 |
| RandomForest | 0.881 | 0.526 | 0.600 | 0.473 | 0.529 |
| XGBoost | 0.877 | 0.510 | 0.560 | 0.452 | 0.500 |

Rainfall trigger model, grouped by location: **AUC 0.756**. Mean 3-day antecedent
rainfall is 79 mm before failures against 30 mm on non-event days.

**Calibration:** Expected Calibration Error **0.040**. Split-conformal prediction at
α = 0.1 achieves empirical coverage **0.901**, and leaves **24%** of cells with an
ambiguous prediction set — cases the model cannot call at that confidence.

---

## 5. The limitation that matters most

Two independent tests disagree, and the disagreement is the most important thing in this
card.

**Predicting the training inventory**, the full 12-feature model is clearly best:
AUC 0.881 / PR-AUC 0.525, against 0.805 / 0.313 for relative relief alone.

**Ranking 106 independent NASA catalog events**, it is not:

| Map | Mean percentile | Top-20% share | Enrichment |
|---|---|---|---|
| SlipSense v2 (ML) | 67.6% | 37.7% | 1.89× |
| Slope raster alone | 68.6% | 46.2% | **2.31×** |
| Relative relief alone | **70.1%** | 45.3% | 2.26× |

All three beat chance decisively (p < 1e-8), so the system carries genuine skill. But the
machine learning **does not beat a single unmodelled terrain variable on data it has
never seen**, and on top-quintile enrichment it does slightly worse.

That pattern is what inventory bias looks like: a flexible model learns the incidental
correlates of *how the 279 points were mapped*, scores well on held-out points sharing
that bias, and gains nothing on independent events. Spatial cross-validation cannot
detect it, because the bias sits in the training and held-out folds alike.

### Resolved: it was measurement noise — but the conclusion still holds

An independent inventory was then built: 42 landslide scars mapped by Sentinel-2 NDVI
change across six Western Ghats areas, located to a 10 m pixel rather than to a district,
and produced by satellite observation rather than by anyone deciding where to walk.

| Map | NASA catalog (±5–50 km) | Sentinel scars (10 m) |
|---|---|---|
| SlipSense v2 (ML) | 67.6% / 1.89× | **84.9% / 3.69×** |
| Slope alone | 68.6% / 2.31× | **88.0% / 4.05×** |
| Relative relief alone | 70.1% / 2.26× | **86.8% / 4.05×** |

The catalog's coordinate error *was* suppressing the measurement: all three maps rise by
17–19 percentile points, and scars fall in the top quintile at 3.7–4.1× chance
(p = 2e-13). The susceptibility surface is considerably better than the earlier figure
implied.

**But the ranking did not change.** Slope alone still scores highest. Removing the noise
lifted all three maps together rather than revealing a hidden ML advantage.

A separate probe also ruled out the most obvious bias mechanism: landslides sit *farther*
from roads than background samples (1,821 m vs 915 m), and `dist_road` ranks 10th of 16
by permutation importance — the inventory is not a record of where somebody drove.
Adding real soil (SoilGrids 250 m), land cover and roads moved AUC by 0.005 and did not
improve PR-AUC at all.

**Standing conclusion: the map is trustworthy and useful; the machine learning is not yet
justified over a slope-and-relief index, which would be simpler and more transparent.**
Caveat: n = 42, and the scars are unverified candidates.

---

## 6. Coverage

The model was trained on inventory falling entirely within **one 1°×1° tile**
(75–76°E, 12–13°N), which intersects only **two** Kerala districts — Kasaragod and
Kannur — plus adjacent Karnataka. 215 of the 279 inventory points lie outside Kerala.

Prediction has been extended to **10 tiles** spanning Kerala's Western Ghats. Those nine
additional tiles are **extrapolation**: no labelled landslide from them informed the
model. Pooled across 106 independent events they perform comparably to the trained tile,
which is evidence the extrapolation is not unreasonable — but it is not the same as
having been validated there.

The system does **not** detect landslides anywhere. It predicts susceptibility. Detection
from satellite imagery is not implemented.

---

## 7. Retracted results

Earlier published figures of **F1 0.832 / Accuracy 85.6% / ROC-AUC 0.958** are invalid
and must not be quoted. Their dataset had 550 of 800 rows fabricated with
`np.random.uniform`, and two features generated *conditional on the label*, so
`dist_river < 1250` separated every synthetic row perfectly. A RandomForest scored
AUC 1.000 on that subset.

Independently, the raster stack was mislabelled: `DEM_filled_75.tif` held slope in
degrees rather than elevation, and `slope75.tif` was computed in EPSG:4326 and pinned at
83–90° everywhere. The deployed susceptibility map ranked real landslide sites at the
**35th percentile** of its own distribution — worse than random. The rebuilt map places
the same sites at the **99.1st**.

`data_preparation.py` and `enhanced_model.py` now refuse to execute. See
`data/RETRACTED_merged_landslide_data.md`.

---

## 8. Operational caveats

- **Alerting** uses calibrated tiers: WATCH 0.446 (5% of terrain, 100% inventory
  recall), HIGH 0.704, VERY HIGH 0.871. Exposure is measured as the *share of district
  area* above HIGH, not the district average, which would be dominated by safe terrain.
- **Rainfall failure is surfaced, not swallowed.** If rainfall cannot be retrieved the
  district reports `UNKNOWN (rainfall unavailable)`, never `LOW`.
- **Runout** parameters (22° reach angle, 70 m drag length, 1.5 m soil) are literature
  defaults for Western Ghats regolith, not calibrated against local measurements.
- **Factor of safety** agrees with the ML map on only **6%** of ML-flagged cells. The two
  are independent lines of evidence and their disagreement is unresolved.
- **Exposure figures** are lower bounds: 12 of 55 OSM query boxes were fetched, and at
  30 m a typical Kerala house is sub-pixel, so building counts merge neighbours.

---

## 9. What would most improve this

1. **Provenance of the 279 points** — determines whether the ML component is justified.
2. **An independent, well-located, dated inventory** (e.g. Sentinel-2 change detection)
   — resolves validation, unlocks IoU/Dice for segmentation, and enables a deployable
   rainfall intensity–duration threshold.
3. **Soil and lithology at usable resolution** — the only soil layer available derives
   from a 30×29 pixel source and was excluded from the model as unusable.

## 10. Reproducing

```
python ml_models/build_terrain_stack.py      # terrain from DEM
python ml_models/build_real_dataset.py       # sample inventory + negatives
python ml_models/train_spatial_cv.py         # spatial-block evaluation
python ml_models/generate_susceptibility_v2.py
python ml_models/generate_runout_v2.py
python ml_models/baseline_comparison.py      # the test that matters most
python ml_models/conformal.py
```
