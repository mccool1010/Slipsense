# RETRACTED: merged_landslide_data.csv

**Do not train on this file. Do not quote any metric derived from it.**

`merged_landslide_data.csv` is the 800-row dataset behind the retracted
**F1 0.832 / Accuracy 85.6% / ROC-AUC 0.958** figures. It is kept only so the record
of what happened stays auditable.

## What is wrong with it

**550 of its 800 rows are fabricated.**

| Source | Rows | Real? |
|---|---|---|
| `primary` | 250 | Real - sampled from rasters |
| `kerala` | 500 | **Fabricated** - 7 of 9 features are `np.random.uniform` |
| `global_catalog_synthetic` | 50 | **Fabricated** - every value random |

**Two features were generated from the label.** In `data_preparation.py`:

```python
elevation  = np.where(landslide == 1, uniform(500, 1400),  uniform(50, 800))
dist_river = np.where(landslide == 1, uniform(200, 1000),  uniform(1500, 2600))
```

The resulting classes do not overlap at all. In the synthetic rows, positives have
`dist_river` at most 998 m and negatives at least 1513 m, so the single rule
`dist_river < 1250` classifies **100.00%** of them correctly. A RandomForest scored
**AUC 1.000** on that subset. The models were reading the answer off label-derived
features rather than learning anything about terrain.

On the 250 genuinely real rows alone, the same RandomForest scored **AUC 0.671,
F1 0.497**. That gap is the entire "+42% improvement" the old documentation claimed.

## What replaces it

`real_landslide_dataset.csv`, built by `ml_models/build_real_dataset.py`: 2,779 rows,
every one a real coordinate sampled against the rebuilt v2 terrain stack, zero
synthetic values. Evaluated with spatial-block cross-validation in
`ml_models/spatial_cv_report.md`.

## Scripts that touch this file

Both are retired and now refuse to execute:

- `ml_models/data_preparation.py` - generated it
- `ml_models/enhanced_model.py` - trained on it

Their retirement notices explain the defects in full.
