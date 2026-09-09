# Augmented Feature Comparison

Whether adding soil, land cover and road proximity closes the gap between
predicting the training inventory and ranking independent events.

| Feature set | n | AUC | PR-AUC | Independent mean pct | Enrichment |
|---|---|---|---|---|---|
| Terrain only | 12 | 0.881 | 0.526 | 51.3% | 0.56x |
| Terrain + soil | 15 | 0.883 | 0.533 | 52.7% | 0.56x |
| Terrain + land cover | 14 | 0.893 | 0.624 | 54.4% | 1.11x |
| Terrain + road | 13 | 0.883 | 0.505 | 55.5% | 0.56x |
| Everything available | 18 | 0.896 | 0.625 | 55.1% | 1.11x |

## Permutation importance

| Feature | Importance |
|---|---|
| forest_fraction | +0.1946 |
| relative_relief | +0.1657 |
| elevation | +0.0529 |
| drainage_density | +0.0507 |
| soil_sand | +0.0189 |
| soil_clay | +0.0185 |
| dist_road **(bias probe)** | +0.0155 |
| soil_index | +0.0148 |
| twi | +0.0066 |
| aspect_east | +0.0064 |
| slope | +0.0052 |
| plan_curvature | +0.0010 |
| flow_acc | +0.0004 |
| bare_fraction | +0.0000 |
| dist_river | -0.0008 |
| profile_curvature | -0.0065 |
| aspect_north | -0.0080 |
| spi | -0.0138 |
