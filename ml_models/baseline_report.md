# Baseline Comparison

Whether the machine learning earns its complexity, tested two ways.
This comparison was absent from the original project: the retracted results
were only compared against other versions of themselves.

## Test 1 - predicting the training inventory (spatial-block CV)

| Model | Features | AUC | PR-AUC |
|---|---|---|---|
| Random scores | 0 | 0.482 | 0.094 |
| Slope only | 1 | 0.699 | 0.243 |
| Relative relief only | 1 | 0.805 | 0.313 |
| Slope + relief | 2 | 0.851 | 0.380 |
| Full model (12 features) | 12 | 0.881 | 0.525 |

## Test 2 - ranking 106 independent NASA catalog events

Scale-free: each map is scored by where independent landslides fall in
its own value distribution, so probability maps, a raw slope raster and
the published GSI product can be compared directly. Random would place
events at the 50th percentile and put 20% in the top quintile.

| Map | n | Mean percentile | Top-20% share | Enrichment | Wilcoxon p |
|---|---|---|---|---|---|
| SlipSense v2 (ML) | 106 | 67.6% | 37.7% | 1.89x | 9.9e-10 |
| Slope raster alone | 106 | 68.6% | 46.2% | 2.31x | 1.6e-08 |
| Relative relief alone | 106 | 70.1% | 45.3% | 2.26x | 2.1e-11 |
| GSI published susceptibility | 82 | 22.1% | 7.3% | 0.37x | 1 |
| Pre-v2 deployed map | 9 | 37.3% | 11.1% | 0.56x | - |

Best on independent events: **Relative relief alone** (70.1th percentile, 2.26x top-quintile enrichment).

## What these two tests together mean

They disagree, and the disagreement is the finding.

**On the training inventory**, the full 12-feature model is clearly best: AUC 0.881 and
PR-AUC 0.525, against 0.805 / 0.313 for relative relief alone. The extra features look
like they are doing real work.

**On 106 independent events, they are not.** The full model reaches the 67.6th
percentile with 1.89x top-quintile enrichment. A raw slope raster - no model, no
training, no features - reaches 68.6% and 2.31x. Relative relief alone reaches 70.1%
and 2.26x. **The machine learning does not beat a single unmodelled terrain variable on
data it has never seen, and on top-quintile enrichment it does slightly worse.**

All three are far better than chance (p < 1e-8), so the system does carry genuine skill.
The question this raises is narrower and sharper: *does the ML earn its complexity?* On
current evidence, no - it wins only where it is scored against the inventory it was
trained on.

That pattern is what inventory bias looks like. If the 279 training points were mapped
preferentially along roads, cuttings or otherwise accessible ground, a flexible model
would learn those incidental correlates, score highly on held-out points that share the
same bias, and gain nothing on independent events that do not. Spatial cross-validation
cannot detect this, because the bias is present in the training and held-out folds
alike.

Two things would settle it, both already on the work list:
- the provenance of the 279 points (item 44) - they carry only an `id`, no source,
  date or accuracy
- an independent, well-located inventory (item 12), which would allow the model to be
  trained and tested on data that does not share one mapping process

Until then, **relative relief is the honest benchmark any model here has to beat**, and
the current model does not beat it out of sample.

### On the GSI comparison

The published GSI susceptibility ranks events *below* chance in this test (22.1st
percentile). That result should be read cautiously rather than as a verdict on the
product. It is a three-class, district-scale zonation, not a 30 m predictive surface;
roughly half its mapped area falls in a single class; our own rasterisation of the
district shapefiles may lose information; and the catalog coordinates carry errors up to
50 km. The comparison is included for completeness, not as a claim that the official
product is wrong.
