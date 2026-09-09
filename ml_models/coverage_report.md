# Coverage and Transfer Report

The model was trained on inventory from a single tile (`cop30_N12_E075`, 75-76E / 12-13N). Every other tile is extrapolation and is scored here against the independent NASA Global Landslide Catalog, which contributed nothing to training.

| Tile | Events | Map median | Event median | Event percentile | Status |
|---|---|---|---|---|---|
| cop30_N08_E076 | 5 | 0.004 | 0.008 | 63.9% | extrapolated |
| cop30_N08_E077 | 4 | 0.019 | 0.008 | 26.7% | extrapolated |
| cop30_N09_E076 | 21 | 0.010 | 0.124 | 78.8% | extrapolated |
| cop30_N09_E077 | 6 | 0.053 | 0.129 | 72.8% | extrapolated |
| cop30_N10_E075 | 0 | 0.004 | nan | - | extrapolated |
| cop30_N10_E076 | 14 | 0.026 | 0.073 | 57.9% | extrapolated |
| cop30_N10_E077 | 3 | 0.044 | 0.184 | 78.4% | extrapolated |
| cop30_N11_E075 | 5 | 0.004 | 0.010 | 71.1% | extrapolated |
| cop30_N11_E076 | 27 | 0.055 | 0.068 | 58.5% | extrapolated |
| cop30_N12_E074 | 12 | 0.004 | 0.021 | 93.7% | extrapolated |
| cop30_N12_E075 | 9 | 0.043 | 0.052 | 53.8% | trained |

A percentile well above 50 means the map ranks real landslides higher than typical terrain on that tile, which is the evidence that the model transfers. Values near 50 mean it does not.
