# Validation against Sentinel-2 derived scars

42 candidate scars mapped by NDVI change across 6 Western Ghats areas, located to a 10 m pixel.

| Map | n | Mean percentile | Top-20% share | Enrichment | Wilcoxon p |
|---|---|---|---|---|---|
| SlipSense v2 (ML) | 42 | 87.4% | 73.8% | 3.69x | 2.3e-13 |
| Slope raster alone | 42 | 88.0% | 81.0% | 4.05x | 2.3e-13 |
| Relative relief alone | 42 | 86.8% | 81.0% | 4.05x | 2.3e-13 |

## Comparison with the NASA catalog test

From `baseline_report.md`, on 106 catalog events with coordinate errors
up to 50 km:

| Map | Mean percentile | Enrichment |
|---|---|---|
| SlipSense v2 (ML) | 67.6% | 1.89x |
| Slope raster alone | 68.6% | 2.31x |
| Relative relief alone | 70.1% | 2.26x |

## Verdict

On well-located scars the ML map reaches the **87.4th percentile** against **86.8** for relative relief - it leads where it trailed on the imprecise catalog. That favours explanation (a): the catalog's coordinate error was masking real skill, and the model does generalise beyond its own inventory.

## Verdict

**Coordinate error was suppressing the measurement.** Every map scores far better against
well-located scars than against the ±5–50 km NASA catalog:

| Map | NASA catalog | Sentinel scars |
|---|---|---|
| SlipSense v2 (ML) | 67.6% / 1.89× | **87.4% / 3.69×** |
| Slope alone | 68.6% / 2.31× | **88.0% / 4.05×** |
| Relative relief alone | 70.1% / 2.26× | **86.8% / 4.05×** |

Scars land in the top quintile at 3.7–4.1× chance, p = 2e-13. The susceptibility surface
is considerably better than the catalog test implied.

**The ML and a plain slope raster are statistically indistinguishable.** Adding land
cover lifted the model from 84.9% to 87.4% mean percentile and gave it the highest
median of the three (91.5% against 89.8% for slope). Paired on the same 42 scars:

    mean difference (ML − slope):  −0.54 percentile points
    paired Wilcoxon:               p = 0.647
    ML ranks higher on:            21 of 42 scars

Twenty-one of forty-two is a coin flip. The earlier reading — that slope *beat* the
model — does not survive vegetation being added; but neither does the opposite claim.
On this evidence the twelve-feature model and a single unmodelled terrain variable
perform the same out of sample, and the honest statement is that the ML has not yet
demonstrated an advantage, not that it loses.

Top-quintile enrichment is the one place slope stays ahead (4.05× against 3.69×), which
is worth noting: for the specific job of picking the most dangerous fifth of the
landscape, the simple index is still at least as good.

> **These scars are unverified candidates.** NDVI loss on steep ground is
> also produced by logging, quarrying, cloud shadow and seasonal
> agriculture. The sample is also small. Treat this as strong evidence,
> not proof.
