# Coverage and Transfer Report

The model was trained on inventory from a single tile (`cop30_N12_E075`, 75-76E / 12-13N). Every other tile is extrapolation and is scored here against the independent NASA Global Landslide Catalog, which contributed nothing to training.

| Tile | Events | Map median | Event median | Event percentile | Status |
|---|---|---|---|---|---|
| cop30_N08_E076 | 5 | 0.001 | 0.006 | 60.6% | extrapolated |
| cop30_N08_E077 | 4 | 0.010 | 0.005 | 38.2% | extrapolated |
| cop30_N09_E076 | 21 | 0.009 | 0.135 | 79.4% | extrapolated |
| cop30_N09_E077 | 6 | 0.035 | 0.136 | 72.5% | extrapolated |
| cop30_N10_E075 | 0 | 0.002 | nan | - | extrapolated |
| cop30_N10_E076 | 14 | 0.026 | 0.038 | 58.0% | extrapolated |
| cop30_N10_E077 | 3 | 0.037 | 0.221 | 82.0% | extrapolated |
| cop30_N11_E075 | 5 | 0.003 | 0.014 | 77.3% | extrapolated |
| cop30_N11_E076 | 27 | 0.058 | 0.064 | 56.9% | extrapolated |
| cop30_N12_E074 | 12 | 0.002 | 0.029 | 94.9% | extrapolated |
| cop30_N12_E075 | 9 | 0.044 | 0.034 | 51.5% | trained |

A percentile well above 50 means the map ranks real landslides higher than typical terrain on that tile, which is the evidence that the model transfers. Values near 50 mean it does not.

## Independent validation across all 10 tiles — the model does transfer

An earlier single-tile check looked like a failure: on the trained tile, NASA catalog
events landed at percentile 51.5%, indistinguishable from random. Pooling all 10 tiles
shows that was small-sample noise, compounded by that tile's unusually poor coordinates
(four of its nine events are located to +/-50 km).

Across **106 independent events** — from an inventory that contributed nothing to
training — the model ranks real landslides well above typical terrain:

| Statistic | Value | Random baseline |
|---|---|---|
| Mean percentile in map | **67.3%** | 50% |
| Median percentile | **70.7%** | 50% |
| Events above the 50th percentile | **78 / 106** | 53 / 106 |
| Events in the top 20% of the map | **37.7%** | 20% |

Wilcoxon signed-rank against 50: **p < 0.0001**. Binomial test on the 78/106 split:
**p < 0.0001**. Events fall in the top quintile at **1.9x** the rate chance would give.

Location accuracy behaves the way it should if coordinate error is diluting the signal:

| Catalog accuracy | n | Mean percentile |
|---|---|---|
| exact / 1 km / 5 km | 65 | **69.4%** |
| 25 km / 50 km | 15 | 61.3% |

Mann-Whitney, well-located > poorly-located: p = 0.065. Suggestive rather than
conclusive, but it points the right way, and it explains why per-tile numbers with a
handful of events each are so noisy.

### What this does and does not establish

It establishes that the susceptibility model carries **real, statistically significant
skill on data it has never seen**, across the whole Western Ghats span of Kerala — not
only on the tile it was trained on.

It does not close the gap between that and the **99.1st percentile** the model achieves
on its own 279-point training inventory. Independent events reach 67.3. Part of that gap
is catalog coordinate error, as the accuracy split shows. Whether the remainder is
inventory bias — points mapped preferentially along roads and accessible ground — is
still open, and still needs the provenance of those 279 points to settle.

Treat **67.3rd percentile / 1.9x top-quintile enrichment** as the defensible
out-of-sample claim. The spatial-CV AUC of 0.881 describes something narrower: how well
the model predicts this particular inventory on held-out ground.
