"""
thresholds.py
Susceptibility class breaks, in one dependency-free place.

These values are consumed by two very different modules: `tiles.py`, which only needs
numpy and PIL to colour a PNG, and `alerts.py`, which pulls in shapely, rasterio and
requests to decide whether to send an SMS. Importing the constants from `alerts` made
tile rendering depend on the entire alerting stack, so a missing shapely install took
down the tile server with it. Keeping them here means neither module imports the other.

They must stay in one place, though: a duplicated copy in `tiles.py` had already fallen
out of step with `alerts.py`, so the map was drawn with one model's cutoffs while alerts
fired on another's.

Recalibrated by ml_models/calibrate_alert_threshold.py whenever the susceptibility map
is regenerated. Cutoffs are chosen by selectivity - the share of terrain each flags -
and checked against how much of the 279-point inventory they recover:

    tier        flags % of terrain   cutoff   catches % of real landslides
    WATCH                     5.0%    0.374                        100.0%
    HIGH                      1.0%    0.619                         84.9%
    VERY HIGH                 0.2%    0.869                         32.6%
"""

SUSCEPTIBILITY_WATCH = 0.374
SUSCEPTIBILITY_HIGH = 0.619
SUSCEPTIBILITY_VERY_HIGH = 0.869

# Ordered breaks, for colour ramps and legends.
SUSCEPTIBILITY_BREAKS = (SUSCEPTIBILITY_WATCH,
                         SUSCEPTIBILITY_HIGH,
                         SUSCEPTIBILITY_VERY_HIGH)
