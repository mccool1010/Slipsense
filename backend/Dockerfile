# SlipSense backend: FastAPI tile server, pixel queries, rainfall and alerting.
#
# Built on python:slim rather than a GDAL base image. rasterio and shapely both ship
# manylinux wheels with GDAL and GEOS statically bundled, so the usual reason for a
# 1.5 GB osgeo/gdal base does not apply here - the wheels supply their own. The result
# is roughly a quarter of the size and there is no chance of the system GDAL and the
# wheel's GDAL disagreeing about versions.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# rasterio's manylinux wheel bundles GDAL and 27 other libraries, but not quite
# everything: the bundled libgdal still dynamically links libexpat, which python:slim
# does not ship. The image then builds cleanly and dies on first import with
#
#   ImportError: libexpat.so.1: cannot open shared object file
#
# which is an unhelpful failure, because nothing in the build log hints at it.
#
# Determined by reading the wheel rather than by guessing: of the 64 shared libraries
# the bundled GDAL references, the only one absent from both the wheel and a slim image
# is libexpat.so.1. The rest - libdl, libm, libgcc_s, libpthread, libstdc++ - already
# come with the Python base image.
#
# curl is only for the container healthcheck below.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl \
      libexpat1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so editing source does not invalidate the wheel layer.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# The served rasters: the 33 MB bundle from ml_models/build_deploy_bundle.py, not the
# ~7 GB development stack. See docs/DEPLOYMENT.md for what is left out and why.
COPY deploy/rasters ./deploy/rasters

# District boundaries, read by the alert system.
COPY Kerala_District_Boundary.geojson ./Kerala_District_Boundary.geojson

COPY backend ./backend

# Point config.py at the bundle instead of the development stack.
ENV SLIPSENSE_RASTER_DIR=/app/deploy/rasters \
    PORT=8000 \
    # Alerting sends real SMS. An exposed endpoint that can spend money should not be
    # armed by default; set DRY_RUN=false deliberately, per environment.
    DRY_RUN=true

WORKDIR /app/backend

EXPOSE 8000

# /health reports each dependency, which rasters resolved, and whether alerting loaded.
# Checking it rather than just the port means a container with missing rasters is
# reported unhealthy instead of silently serving empty tiles.
#
# The pattern tolerates optional whitespace on purpose: FastAPI serialises compactly as
# `"ok":true`, so matching `"ok": true` never fires and marks every healthy container
# unhealthy - which fails the deploy for a reason that looks nothing like a formatting
# difference.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/health" | grep -qE '"ok":[[:space:]]*true' || exit 1

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
