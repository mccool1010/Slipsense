# Spatial Cross-Validation Report

All rows are real coordinates sampled against the rebuilt v2 terrain stack.
No synthetic samples. Metrics are out-of-fold.

- Samples: **2779** (279 landslide, 2500 non-landslide)
- Spatial blocks: 497 at 5.0 km, 5 folds
- Features: 17

## Spatial CV (honest estimate)

| Model | AUC | PR-AUC | Precision | Recall | F1 | Brier |
|---|---|---|---|---|---|---|
| RandomForest | 0.895 | 0.636 | 0.645 | 0.541 | 0.589 | 0.058 |
| XGBoost | 0.892 | 0.609 | 0.689 | 0.470 | 0.559 | 0.060 |
| LightGBM | 0.882 | 0.599 | 0.574 | 0.530 | 0.551 | 0.066 |

## Random CV (optimistic - shown for comparison only)

| Model | AUC | PR-AUC | Precision | Recall | F1 |
|---|---|---|---|---|---|
| RandomForest | 0.892 | 0.646 | 0.697 | 0.520 | 0.595 |
| XGBoost | 0.887 | 0.627 | 0.747 | 0.455 | 0.566 |
| LightGBM | 0.880 | 0.619 | 0.653 | 0.498 | 0.565 |

## Permutation importance (best model, spatial holdout)

| Feature | Importance | Std |
|---|---|---|
| forest_fraction | +0.2126 | 0.0157 |
| relative_relief | +0.2024 | 0.0305 |
| elevation | +0.0624 | 0.0188 |
| drainage_density | +0.0549 | 0.0150 |
| soil_clay | +0.0301 | 0.0170 |
| soil_sand | +0.0164 | 0.0168 |
| soil_index | +0.0133 | 0.0099 |
| twi | +0.0068 | 0.0125 |
| bare_fraction | +0.0000 | 0.0000 |
| aspect_east | -0.0005 | 0.0058 |
| flow_acc | -0.0026 | 0.0061 |
| dist_river | -0.0033 | 0.0141 |
| slope | -0.0061 | 0.0123 |
| plan_curvature | -0.0079 | 0.0062 |
| aspect_north | -0.0127 | 0.0049 |
| profile_curvature | -0.0137 | 0.0084 |
| spi | -0.0192 | 0.0063 |
