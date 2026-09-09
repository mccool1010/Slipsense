# Deprecated rasters and models — do not consume

Everything listed here is retained for audit only. Nothing in the current pipeline reads
it, and nothing new should.

## Mislabelled terrain rasters

The names do not describe the contents. This is what produced the retracted results.

| File | Name says | Actually contains |
|---|---|---|
| `DEM_filled_75.tif` | filled elevation | **slope in degrees** (0–74, median 7.05) |
| `slope75.tif` | slope | slope computed in EPSG:4326, so horizontal units are degrees and vertical metres — **pinned at 83–90° everywhere** |
| `Distance_to_River_75.tif` | distance to river | **binary 0/1 mask**, not a distance surface |
| `SCA75.tif` | specific catchment area | **entirely nodata** |
| `curvature75.sdat` | curvature | uint8 with 3 classes, not continuous curvature |

The real DEM for this tile is `reprojected75.tif` / `hydrology75.tif` (0–1620 m).

**Replacement:** `backend/rasters/v2/`, rebuilt from Copernicus GLO-30 by
`ml_models/build_terrain_stack.py`. All layers share one EPSG:32643 grid in metric units.

## Superseded susceptibility maps

| File | Problem |
|---|---|
| `susceptibility_ml.tif` | Trained on the fabricated dataset and fed the mislabelled rasters. Ranks real landslide sites at the **35th percentile** of its own distribution — worse than random. |
| `susceptibility_dl.tif` | Output of an autoencoder, not a classifier. Ranks real landslides at the **41st percentile**. |

Both are still reachable in `config.py` as `susceptibility_ml_legacy` /
`susceptibility_dl_legacy` purely so the comparison figure can be regenerated.

**Replacement:** `backend/rasters/v2/susceptibility_ml.tif` (99.1st percentile on the
same inventory) and `v2/susceptibility_dl.tif`.

## Superseded runout layers

`hazard_fused.tif`, `transit_mask.tif`, `deposition_mask.tif`, `runout_paths.geojson`
in this directory were produced by `generate_runout_and_fuse.py`, which routed debris
across `DEM_filled_75.tif` — a slope raster treated as elevation — and whose deposition
rule (`slope < 20°`) tested a raster that never drops below 83°, so deposition could
never trigger.

**Replacement:** the same filenames under `backend/rasters/v2/`, from
`ml_models/generate_runout_v2.py`.

## Deprecated models

| File | Problem |
|---|---|
| `ml_models/enhanced_model.pkl`, `enhanced_scaler.pkl` | Trained on the leaked dataset; source F1 0.832 / AUC 0.958 retracted |
| `ml_models/legacy_landslide_model_rf.pkl`, `_xgb.pkl`, `_optimized.pkl`, `legacy_scaler.pkl` | Trained on the mislabelled rasters |
| `backend/rasters/unet_refiner.pth` | Autoencoder weights; the network reproduced its own input |

**Replacement:** `ml_models/susceptibility_model.pkl`,
`ml_models/rainfall_trigger_model.pkl`, `backend/rasters/cnn_context.pt`.

See `docs/MODEL_CARD.md` for verified figures and
`data/RETRACTED_merged_landslide_data.md` for the dataset defect in full.
