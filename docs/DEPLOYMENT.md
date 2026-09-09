# Deploying SlipSense

Backend on Render, frontend on Vercel. Neither requires a payment method.
Fly.io config is kept too, for when a card is available - it gives a warmer machine
nearer to Kerala.

## What actually gets deployed

The generated raster stack is about **7 GB**, which made hosting look impractical.
Almost none of it is served:

| Path | Size | Deployed? |
|---|---|---|
| `backend/rasters/tiles/` | 6.8 GB | No — per-tile Kerala predictions, used only for validation |
| `data/dem/` | 705 MB | No — source DEMs |
| `backend/rasters/v2/` | 1.1 GB | No — the development stack |
| **`deploy/rasters/`** | **33 MB** | **Yes** — the only thing the API reads |

`ml_models/build_deploy_bundle.py` produces that bundle: the nine layers named in
`config.RASTERS`, as Cloud-Optimised GeoTIFFs with overviews, quantised to uint8 where
the values allow.

| | Size | z9 tile | z11 tile | z13 tile |
|---|---|---|---|---|
| Development stack | 181 MB | 0.307 s | 0.107 s | 0.047 s |
| **Deploy bundle** | **33 MB** | **0.035 s** | **0.069 s** | **0.025 s** |

82% smaller and roughly 9x faster at regional zoom, because the originals have no
overviews and a low-zoom tile has to be assembled from full-resolution data.

The precision cost is one quantisation step: a susceptibility of 0.891 reads back as
0.889, in the same VERY HIGH class. Readers undo the scaling automatically
(`backend/rasterscale.py`), so development against the float32 stack and production
against the bundle behave identically.

## Rebuild the bundle

Needed whenever the model is retrained or the rasters regenerated:

```bash
python ml_models/build_deploy_bundle.py
```

Then commit `deploy/rasters/`. It is deliberately **excluded from Git LFS**
(`.gitattributes`): build platforms clone without pulling LFS by default, and pointer
files where the container expects rasters fail at runtime as empty tiles rather than at
build time.

## Backend — Render (no payment method required)

Fly.io was the first choice, but it now refuses to place a machine without a card on
file:

```
The following problems must be fixed in the Launch UI:
 * failed to determine region: failed to get placements:
   requested machine count exceeds organization limit
! You'll need to add a payment method in order to proceed.
```

Render's free instance still needs no card and builds the same Dockerfile.

1. render.com → **New** → **Blueprint**
2. Connect `mccool1010/Slipsense`, branch `rebuild/honest-pipeline`
3. Render reads `render.yaml`; approve the plan
4. Add `OPENWEATHER_API_KEY` in the dashboard (it is marked `sync: false`, so it is
   never committed)

Then check `https://<service>.onrender.com/health` for `"ok":true`.

**The free instance sleeps after ~15 minutes idle** and takes 30-60 seconds to wake. The
first map load after a quiet period shows empty tiles until the container is up - which
looks identical to the coverage bug this project already has history with. Before
showing it to anyone, open `/health` and wait for a response.

### Alternative: Hugging Face Spaces

Also free and card-free, with more memory and no sleep, but it deploys from a separate
Hugging Face git repository rather than from GitHub, so it needs its own push. Worth it
if the sleep is a problem.

## Backend — Fly.io (needs a payment method)

```bash
fly auth login
fly launch --no-deploy          # keeps the committed fly.toml
fly deploy
```

`fly.toml` uses Singapore (`sin`), the closest region Fly still offers to Kerala —
Mumbai (`bom`) was retired and naming it aborts `fly launch` outright. It keeps one
machine warm, because a cold start on the first tile request makes the map look broken.

Secrets, none of which belong in the image:

```bash
fly secrets set OPENWEATHER_API_KEY=...
# Only if alerting should actually send SMS. It is dry-run by default.
fly secrets set DRY_RUN=false VONAGE_API_KEY=... VONAGE_API_SECRET=... \
                ALERT_RECIPIENTS=+91XXXXXXXXXX
```

Verify with `curl https://<app>.fly.dev/health` — it reports every dependency, which
rasters resolved, and whether alerting loaded. The container healthcheck runs the same
endpoint, so a machine with a broken bundle is marked unhealthy instead of quietly
serving empty tiles.

### Why python:slim rather than a GDAL base image

`rasterio` and `shapely` ship manylinux wheels with GDAL and GEOS bundled, so the usual
reason for a 1.5 GB `osgeo/gdal` base does not apply. The image is roughly a quarter of
the size, and there is no chance of a system GDAL disagreeing with the wheel's.

## Frontend — Vercel

Import the repository, set the root directory to `frontend/`, and add:

```
VITE_TILE_SERVER=https://<service>.onrender.com
VITE_CESIUM_ION_TOKEN=<token>
```

`vercel.json` handles the Vite build and SPA rewrites.

Both variables are optional in the sense that the app degrades rather than breaking:
without a Cesium token the 3D view falls back to open terrarium elevation tiles, and
without a reachable backend the base map still renders.

**The Cesium token will be visible in the built bundle.** Vite inlines `VITE_*` values
at build time; that is inherent to a browser-side key, not a mistake. Restrict it in the
Cesium Ion console to the assets actually used rather than relying on it staying secret.

## Alternatives

**Railway** also works and does not sleep, but has no Indian region, so tiles are served
from further away.

**Object storage** — S3 or Cloudflare R2 with `rio-tiler` reading over `/vsicurl/` — is
worth it only if the bundle grows well beyond a few hundred megabytes. At 33 MB, baking
it into the image is simpler and faster.

## Checks before going live

- `python -m pytest tests/ -v` — 21 tests
- `curl .../health` returns `"ok":true` with no missing layers
- A tile inside the modelled footprint returns real data, e.g.
  `/tiles/susceptibility_ml/11/1453/952.png`
- A tile outside it returns a transparent 334-byte PNG rather than a 500
- `DRY_RUN` is `true` unless SMS is deliberately wanted — an exposed endpoint that can
  spend money should not be armed by default

## Known constraints

- **Modelled coverage is one 1°x1° tile** (75–76°E, 12–13°N). Everything outside it is
  legitimately transparent; the map fits itself to that footprint on load and outlines
  it, so empty is distinguishable from broken.
- **The repository is ~123 MB** because the virtualenv and superseded rasters are
  tracked in LFS. It does not affect the deployment — `.dockerignore` excludes them —
  but a fresh clone is slow.
