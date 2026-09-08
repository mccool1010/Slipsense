# Calibration and Conformal Uncertainty

Out-of-fold under spatial blocks, 2779 samples, alpha = 0.1.

**Expected Calibration Error: 0.0365**

| Probability bin | n | Mean predicted | Observed frequency |
|---|---|---|---|
| 0.0-0.1 | 1779 | 0.033 | 0.017 |
| 0.1-0.2 | 416 | 0.146 | 0.086 |
| 0.2-0.3 | 221 | 0.248 | 0.172 |
| 0.3-0.4 | 129 | 0.344 | 0.178 |
| 0.4-0.5 | 67 | 0.452 | 0.388 |
| 0.5-0.6 | 41 | 0.552 | 0.488 |
| 0.6-0.7 | 30 | 0.640 | 0.633 |
| 0.7-0.8 | 26 | 0.751 | 0.769 |
| 0.8-0.9 | 38 | 0.851 | 0.921 |
| 0.9-1.0 | 32 | 0.943 | 0.969 |

## Conformal prediction sets

- Thresholds: q0 = 0.2639, q1 = 0.9109
- Empirical coverage: **0.901** (guarantee: 0.90)
- Ambiguous sets, containing both labels: **0.229**
- Empty sets: 0.000

- Ambiguous share of the trained tile: **22.34%** (`backend/rasters/v2/uncertainty.tif`)

An ambiguous cell is one the model cannot separate at the requested
confidence. Shading those distinctly is more honest than painting a
single number everywhere, and it matters most on the nine extrapolated
tiles, where the model was never trained and does not beat relative
relief out of sample.
