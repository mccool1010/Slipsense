"""
build_rainfall_dataset.py
Assemble a rainfall-triggering dataset: dated landslides paired with the rain that
preceded them, against matched non-event days at the same places.

Static susceptibility answers *where* a slope can fail. It cannot answer *when*,
because terrain does not change between a quiet January and the August a hillside
collapses. Almost every landslide in the Western Ghats is rainfall triggered, so the
timing signal lives in antecedent rainfall, not in the DEM.

Positives  dated landslide events from the NASA Global Landslide Catalog in the
           Western Ghats window, each with the rainfall history up to its event date
Negatives  the same locations on random dates with no recorded landslide, drawn from
           the monsoon season so the model must learn more than "it rains in June"

Rainfall comes from the Open-Meteo historical reanalysis archive (no API key, daily
totals back to 1940).

Output: data/rainfall_trigger_dataset.csv

Run:  python ml_models/build_rainfall_dataset.py [--neg-per-pos 4]
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "Global_Landslide_Catalog_Export_rows.csv"
OUTPUT = ROOT / "data" / "rainfall_trigger_dataset.csv"
CACHE = ROOT / "data" / "rainfall_cache.json"

# Western Ghats window: Kerala plus the Karnataka/Tamil Nadu flanks of the same range.
BOUNDS = {"min_lat": 8.0, "max_lat": 13.5, "min_lon": 74.5, "max_lon": 77.5}

API = "https://archive-api.open-meteo.com/v1/archive"
WINDOWS = [1, 3, 5, 7, 10, 15, 30, 60, 90]   # antecedent rainfall windows, days
MONSOON_MONTHS = (5, 6, 7, 8, 9, 10, 11)
SEED = 42


def load_cache():
    return json.loads(CACHE.read_text()) if CACHE.exists() else {}


def save_cache(cache):
    CACHE.write_text(json.dumps(cache))


def fetch_series(lat, lon, start, end, cache, session):
    """Daily precipitation for one location and date range, cached on disk.

    Coordinates are rounded to ~1 km, which is finer than the reanalysis grid, so many
    nearby events share a cache entry instead of re-requesting the same cell.
    """
    key = f"{round(lat, 2)}_{round(lon, 2)}_{start}_{end}"
    if key in cache:
        return cache[key]

    params = {"latitude": round(lat, 2), "longitude": round(lon, 2),
              "start_date": start, "end_date": end,
              "daily": "precipitation_sum", "timezone": "Asia/Kolkata"}
    for attempt in range(5):
        try:
            r = session.get(API, params=params, timeout=90)
            if r.status_code == 429:
                time.sleep(20 * (attempt + 1))
                continue
            r.raise_for_status()
            daily = r.json().get("daily", {})
            series = {"time": daily.get("time", []),
                      "precip": [0.0 if v is None else float(v)
                                 for v in daily.get("precipitation_sum", [])]}
            cache[key] = series
            return series
        except requests.RequestException:
            time.sleep(5 * (attempt + 1))
    return None


def antecedent(series, target_date):
    """Rainfall totals over each window ending on the target date."""
    if not series or not series["time"]:
        return None
    times = pd.to_datetime(series["time"])
    precip = np.asarray(series["precip"], dtype=float)
    idx = np.searchsorted(times, pd.Timestamp(target_date))
    if idx >= len(precip):
        idx = len(precip) - 1
    if idx < max(WINDOWS):
        return None

    feats = {f"rain_{w}d": float(precip[idx - w + 1:idx + 1].sum()) for w in WINDOWS}
    feats["rain_event_day"] = float(precip[idx])
    # Intensity relative to the site's own wet-season baseline: 150 mm means something
    # very different on a dry ridge than in a place that averages 150 mm a week.
    baseline = float(np.mean(precip[max(0, idx - 365):idx + 1])) or 1e-6
    feats["rain_3d_ratio"] = feats["rain_3d"] / (baseline * 3)
    feats["rain_15d_ratio"] = feats["rain_15d"] / (baseline * 15)
    return feats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--neg-per-pos", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="cap positives (for testing)")
    args = ap.parse_args()

    rng = np.random.default_rng(SEED)
    cache = load_cache()
    session = requests.Session()

    df = pd.read_csv(CATALOG, low_memory=False)
    region = df[
        (df.latitude >= BOUNDS["min_lat"]) & (df.latitude <= BOUNDS["max_lat"])
        & (df.longitude >= BOUNDS["min_lon"]) & (df.longitude <= BOUNDS["max_lon"])
    ].copy()
    region["date"] = pd.to_datetime(region["event_date"], format="mixed", errors="coerce")
    region = region.dropna(subset=["date"])
    # The reanalysis archive starts in 1940, but catalog coordinates before ~2007 are
    # coarse; keep the window where both are reliable.
    region = region[region.date >= "2007-01-01"]
    if args.limit:
        region = region.head(args.limit)

    print(f"Dated landslide events in the Western Ghats window: {len(region)}")
    if region.empty:
        raise SystemExit("No dated events found")

    rows = []
    for i, (_, ev) in enumerate(region.iterrows(), 1):
        lat, lon, date = float(ev.latitude), float(ev.longitude), ev.date
        start = (date - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
        end = date.strftime("%Y-%m-%d")
        series = fetch_series(lat, lon, start, end, cache, session)
        feats = antecedent(series, date)
        if feats:
            feats.update(lat=lat, lon=lon, date=end, landslide=1,
                         trigger=ev.get("landslide_trigger"),
                         size=ev.get("landslide_size"))
            rows.append(feats)

        # Matched non-event days at the same place, so location is not a confound.
        for _ in range(args.neg_per_pos):
            for _try in range(8):
                offset = int(rng.integers(-1500, -30))
                nd = date + pd.Timedelta(days=offset)
                if nd.month in MONSOON_MONTHS:
                    break
            n_start = (nd - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
            n_end = nd.strftime("%Y-%m-%d")
            nseries = fetch_series(lat, lon, n_start, n_end, cache, session)
            nfeats = antecedent(nseries, nd)
            if nfeats:
                nfeats.update(lat=lat, lon=lon, date=n_end, landslide=0,
                              trigger=None, size=None)
                rows.append(nfeats)

        if i % 10 == 0:
            print(f"  {i}/{len(region)} events, {len(rows)} rows, "
                  f"{len(cache)} cached series", flush=True)
            save_cache(cache)

    save_cache(cache)
    out = pd.DataFrame(rows)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUT, index=False)

    print(f"\nWrote {OUTPUT.relative_to(ROOT)}")
    print(f"  rows {len(out)}  positive {int(out.landslide.sum())}  "
          f"negative {int((out.landslide == 0).sum())}")
    cols = [f"rain_{w}d" for w in (1, 3, 7, 15, 30)]
    print("\nMean antecedent rainfall (mm) by class:")
    print(out.groupby("landslide")[cols].mean().T.to_string())


if __name__ == "__main__":
    main()
