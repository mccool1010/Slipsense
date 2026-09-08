# Patch CNN Report

Terrain-context CNN over 32x32 cell patches (960 m across), 6 channels, spatial-block CV.

Replaces `unet_refine.py`, which was an autoencoder on its own input and could
not produce IoU or Dice. IoU/Dice remain unavailable until the inventory has
mapped scar polygons rather than 279 points.

| Metric | Value |
|---|---|
| AUC | 0.896 |
| PR-AUC | 0.593 |
| Precision | 0.556 |
| Recall | 0.556 |
| F1 | 0.556 |
