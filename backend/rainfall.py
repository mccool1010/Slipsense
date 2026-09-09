"""
rainfall.py
Rainfall retrieval with real antecedent history, honest failure, and no hardcoded key.

Replaces the rainfall handling that lived in alerts.py, which had five defects:

1. It reported `rain["1h"] * 24` as the 24-hour total - one wet hour extrapolated to a
   whole day, turning a 5 mm shower into a claimed 120 mm.
2. It took `max()` of that extrapolation and a genuine 24 h forecast sum, mixing two
   incompatible quantities and biasing high.
3. It fetched only ~24 hours, so the trained rainfall model - which needs 1/3/7/15/30/
   60/90-day antecedent windows - could not be fed at all. Western Ghats failures follow
   multi-day soil saturation, not one afternoon.
4. It sampled a single point per district, the polygon centroid, across terrain with
   severe orographic gradients.
5. On any API failure it logged a warning and returned 0.0 mm, so a revoked key or a
   rate limit made rainfall read as zero and alerts fall silent with nothing surfaced.
   For a warning system that is the most dangerous failure mode available.

Antecedent totals come from the Open-Meteo archive and forecast APIs, which need no key.
Every result carries provenance and staleness, and a failure raises rather than
returning a number that means "dry".
"""

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

import requests

logger = logging.getLogger(__name__)

ARCHIVE_API = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_API = "https://api.open-meteo.com/v1/forecast"

# Antecedent windows the trained model expects (ml_models/train_rainfall_model.py).
WINDOWS = (1, 3, 5, 7, 10, 15, 30, 60, 90)

# The reanalysis archive lags real time by a few days; the forecast API covers the gap
# with its `past_days` window.
ARCHIVE_LAG_DAYS = 6
MAX_STALENESS_HOURS = 12
CACHE_TTL_SECONDS = 1800

_cache: Dict[str, Tuple[float, "RainfallObservation"]] = {}


class RainfallUnavailable(RuntimeError):
    """Raised when rainfall genuinely could not be retrieved.

    Deliberately an exception rather than a 0.0 return: zero millimetres is a real,
    actionable measurement meaning "dry", and a failed lookup must never be
    indistinguishable from one.
    """


@dataclass
class RainfallObservation:
    """Rainfall at one location, with everything needed to judge whether to trust it."""

    lat: float
    lon: float
    antecedent_mm: Dict[str, float]
    retrieved_at: datetime
    last_observation: date
    source: str
    degraded: bool = False
    notes: List[str] = field(default_factory=list)

    @property
    def rain_24h(self) -> float:
        return self.antecedent_mm.get("rain_1d", 0.0)

    @property
    def age_hours(self) -> float:
        return (datetime.now(timezone.utc) - self.retrieved_at).total_seconds() / 3600.0

    @property
    def is_stale(self) -> bool:
        return self.age_hours > MAX_STALENESS_HOURS

    def as_dict(self) -> dict:
        return {
            "lat": self.lat, "lon": self.lon,
            "antecedent_mm": {k: round(v, 1) for k, v in self.antecedent_mm.items()},
            "rain_24h_mm": round(self.rain_24h, 1),
            "retrieved_at": self.retrieved_at.isoformat(),
            "last_observation": self.last_observation.isoformat(),
            "source": self.source, "degraded": self.degraded,
            "age_hours": round(self.age_hours, 2), "stale": self.is_stale,
            "notes": self.notes,
        }


def _get_json(url: str, params: dict, timeout: int = 30, attempts: int = 3) -> dict:
    last = None
    for i in range(attempts):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 429:
                time.sleep(3 * (i + 1))
                last = RainfallUnavailable("rate limited")
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as exc:
            last = exc
            time.sleep(2 * (i + 1))
    raise RainfallUnavailable(f"{url} failed after {attempts} attempts: {last}")


def _daily_series(lat: float, lon: float, start: date, end: date) -> Dict[date, float]:
    """Daily precipitation totals, stitching the archive to the recent forecast window.

    The archive is authoritative but lags several days; the forecast endpoint serves
    recent past days. Neither alone spans "90 days ago until today".
    """
    series: Dict[date, float] = {}
    notes: List[str] = []

    archive_end = min(end, date.today() - timedelta(days=ARCHIVE_LAG_DAYS))
    if archive_end >= start:
        data = _get_json(ARCHIVE_API, {
            "latitude": round(lat, 4), "longitude": round(lon, 4),
            "start_date": start.isoformat(), "end_date": archive_end.isoformat(),
            "daily": "precipitation_sum", "timezone": "Asia/Kolkata",
        })
        daily = data.get("daily", {})
        for d, v in zip(daily.get("time", []), daily.get("precipitation_sum", [])):
            series[date.fromisoformat(d)] = 0.0 if v is None else float(v)

    past_days = min(92, max(1, (end - archive_end).days + ARCHIVE_LAG_DAYS + 1))
    data = _get_json(FORECAST_API, {
        "latitude": round(lat, 4), "longitude": round(lon, 4),
        "daily": "precipitation_sum", "past_days": past_days,
        "forecast_days": 1, "timezone": "Asia/Kolkata",
    })
    daily = data.get("daily", {})
    for d, v in zip(daily.get("time", []), daily.get("precipitation_sum", [])):
        day = date.fromisoformat(d)
        if day <= end:
            series.setdefault(day, 0.0 if v is None else float(v))

    if not series:
        raise RainfallUnavailable("no precipitation values returned")
    return series, notes


def get_rainfall(lat: float, lon: float, on: Optional[date] = None,
                 use_cache: bool = True) -> RainfallObservation:
    """Antecedent rainfall at one point. Raises RainfallUnavailable on failure."""
    on = on or date.today()
    key = f"{round(lat, 3)}:{round(lon, 3)}:{on.isoformat()}"
    if use_cache and key in _cache:
        cached_at, obs = _cache[key]
        if time.time() - cached_at < CACHE_TTL_SECONDS:
            return obs

    start = on - timedelta(days=max(WINDOWS) + 2)
    series, notes = _daily_series(lat, lon, start, on)

    antecedent: Dict[str, float] = {}
    for win in WINDOWS:
        days = [on - timedelta(days=i) for i in range(win)]
        present = [series[d] for d in days if d in series]
        if len(present) < max(1, int(0.8 * win)):
            # Too many gaps for this window to mean anything; omit rather than
            # silently under-report a total that drives an alert.
            notes.append(f"rain_{win}d incomplete ({len(present)}/{win} days)")
            continue
        antecedent[f"rain_{win}d"] = float(sum(present))

    if "rain_1d" not in antecedent:
        raise RainfallUnavailable("no usable 24-hour total")

    baseline = sum(series.values()) / max(len(series), 1) or 1e-6
    if "rain_3d" in antecedent:
        antecedent["rain_3d_ratio"] = antecedent["rain_3d"] / (baseline * 3)
    if "rain_15d" in antecedent:
        antecedent["rain_15d_ratio"] = antecedent["rain_15d"] / (baseline * 15)
    antecedent["rain_event_day"] = series.get(on, antecedent["rain_1d"])

    obs = RainfallObservation(
        lat=lat, lon=lon, antecedent_mm=antecedent,
        retrieved_at=datetime.now(timezone.utc),
        last_observation=max(series),
        source="open-meteo archive+forecast",
        degraded=bool(notes), notes=notes,
    )
    _cache[key] = (time.time(), obs)
    return obs


def sample_area(points: Sequence[Tuple[float, float]],
                on: Optional[date] = None) -> List[RainfallObservation]:
    """Rainfall at several points across an area.

    A district centroid is not representative in the Western Ghats: orographic gradients
    mean one flank can take 200 mm while the centroid stays dry. Callers should pass
    several points and aggregate on the maximum, not the mean.
    """
    out, failures = [], []
    for lat, lon in points:
        try:
            out.append(get_rainfall(lat, lon, on))
        except RainfallUnavailable as exc:
            failures.append(f"({lat:.3f},{lon:.3f}): {exc}")
    if not out:
        raise RainfallUnavailable(
            f"all {len(points)} sample points failed: {'; '.join(failures[:3])}")
    if failures:
        for obs in out:
            obs.degraded = True
            obs.notes.append(f"{len(failures)} of {len(points)} sample points failed")
    return out


def worst_case(observations: Sequence[RainfallObservation]) -> RainfallObservation:
    """The wettest sample. Alerting should follow the worst point, not the average."""
    if not observations:
        raise RainfallUnavailable("no observations to reduce")
    return max(observations, key=lambda o: o.rain_24h)


def health() -> dict:
    """Liveness probe for the rainfall dependency, so silence is never mistaken for calm."""
    probe_lat, probe_lon = 11.6, 76.1     # Wayanad
    started = time.time()
    try:
        obs = get_rainfall(probe_lat, probe_lon, use_cache=False)
        return {
            "ok": True, "degraded": obs.degraded,
            "latency_ms": round((time.time() - started) * 1000),
            "last_observation": obs.last_observation.isoformat(),
            "windows_available": sorted(obs.antecedent_mm),
            "notes": obs.notes,
        }
    except RainfallUnavailable as exc:
        logger.error("Rainfall health check failed: %s", exc)
        return {"ok": False, "error": str(exc),
                "latency_ms": round((time.time() - started) * 1000)}


# Retained only so an existing deployment that still sets it does not break; the value
# is unused. The previous code embedded a live OpenWeather key as a literal default.
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
