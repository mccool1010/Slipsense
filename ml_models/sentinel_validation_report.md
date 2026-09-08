# Validation against Sentinel-2 derived scars

42 candidate scars mapped by NDVI change across 6 Western Ghats areas, located to a 10 m pixel.

| Map | n | Mean percentile | Top-20% share | Enrichment | Wilcoxon p |
|---|---|---|---|---|---|
| SlipSense v2 (ML) | 42 | 84.9% | 73.8% | 3.69x | 2.3e-13 |
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

## Verdict — both things are true

**Coordinate error was suppressing the measurement, substantially.** Every map jumps
when scored against well-located scars instead of the imprecise catalog:

| Map | NASA catalog (±5–50 km) | Sentinel scars (10 m) | Change |
|---|---|---|---|
| SlipSense v2 (ML) | 67.6% / 1.89× | **84.9% / 3.69×** | +17.3 pts |
| Slope alone | 68.6% / 2.31× | **88.0% / 4.05×** | +19.4 pts |
| Relative relief alone | 70.1% / 2.26× | **86.8% / 4.05×** | +16.7 pts |

So explanation (a) is confirmed: the catalog's ±5–50 km coordinates were masking real
skill, and the susceptibility surface is considerably better than the earlier number
suggested. Scars land in the top quintile at **3.7–4.1×** the rate chance would give,
at p = 2e-13.

**But the ordering did not change.** Slope alone still scores highest — 88.0% against
84.9% for the twelve-feature model — and both single-variable baselines beat it on
top-quintile enrichment (4.05× against 3.69×). Removing the measurement noise did not
reveal a hidden ML advantage; it lifted all three maps together and left the ranking
intact.

**What this means.** The system works: it identifies dangerous terrain far better than
chance, on data collected by a completely different process from its training inventory.
The *machine learning* still does not earn its complexity over slope. On present
evidence the defensible claim is about the susceptibility product, not about the model
class — and a slope-and-relief index would be simpler, more transparent, and at least as
accurate out of sample.

That said, n = 42 is small and these are unverified candidates, so this ranks as strong
evidence rather than a settled result.

> **These scars are unverified candidates.** NDVI loss on steep ground is
> also produced by logging, quarrying, cloud shadow and seasonal
> agriculture. The sample is also small. Treat this as strong evidence,
> not proof.
