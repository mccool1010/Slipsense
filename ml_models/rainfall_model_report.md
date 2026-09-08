# Rainfall Triggering Model

Answers *when*, where the susceptibility map answers *where*.
Cross-validation is grouped by location, so every score is on sites whose
rainfall history the model has not seen.

- Rows: **545** (109 landslide days, 436 matched non-event days)
- Distinct locations: 64
- Rainfall source: Open-Meteo historical reanalysis (daily totals)

## Model comparison (location-grouped CV)

| Model | AUC | PR-AUC | Precision | Recall | F1 |
|---|---|---|---|---|---|
| LogisticRegression | 0.738 | 0.502 | 0.451 | 0.587 | 0.510 |
| RandomForest | 0.756 | 0.504 | 0.505 | 0.505 | 0.505 |
| GradientBoosting | 0.740 | 0.503 | 0.479 | 0.514 | 0.496 |

## Mean antecedent rainfall (mm)

| Window | Non-event day | Landslide day | Ratio |
|---|---|---|---|
| 1 day | 10.3 | 30.7 | 2.99x |
| 3 day | 30.4 | 79.1 | 2.61x |
| 7 day | 74.0 | 136.1 | 1.84x |
| 15 day | 163.4 | 235.7 | 1.44x |
| 30 day | 321.3 | 399.8 | 1.24x |

## Intensity-duration threshold

Fitted lower envelope: **I = 2.18 · D^-0.151** (I in mm/day, D in days)

| Duration (days) | Envelope intensity (mm/day) | Envelope total (mm) | Median at real events (mm/day) |
|---|---|---|---|
| 1 | 2.18 | 2.2 | 18.6 |
| 3 | 1.85 | 5.5 | 20.8 |
| 7 | 1.63 | 11.4 | 17.0 |
| 15 | 1.45 | 21.8 | 14.2 |
| 30 | 1.31 | 39.2 | 12.2 |

> **Do not deploy the envelope as an operational trigger.** Its shape is correct - intensity falls with duration, as it must - but its absolute level is far too low, and a threshold of ~2 mm/day would fire almost every monsoon day. The cause is inventory quality, not the fit: NASA catalog entries carry coarse location accuracy and uncertain dates, so some 'events' pair with grid cells and days that saw almost no rain, and those points drag any lower envelope toward zero.

The **median column is the more honest operational reference**: real failures here cluster around 19 mm in 24 h and 62 mm over 3 days. A deployable threshold needs a dated inventory with mapped coordinates - the same prerequisite as IoU/Dice for the segmentation model.
