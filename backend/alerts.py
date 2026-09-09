"""
District-wise Emergency SMS Alert System for SlipSense

This module provides landslide alert functionality that:
1. Analyzes v2 susceptibility within each district
2. Checks for hazardous zones (Failure/Transit) in the fused hazard raster
3. Fetches rainfall, with antecedent history, via the `rainfall` module (Open-Meteo)
4. Sends SMS alerts when risk thresholds are exceeded

ALERT TRIGGER CONDITIONS (ALL must be true):
- At least DISTRICT_AREA_FRACTION of the district's sampled area exceeds
  SUSCEPTIBILITY_HIGH, OR any sample exceeds SUSCEPTIBILITY_VERY_HIGH
- Rainfall >= RAINFALL_THRESHOLD_MM in 24 hours (60% of that if soil is clay-rich),
  OR 15-day antecedent rainfall >= ANTECEDENT_15D_THRESHOLD_MM
- District contains Failure (3) or Transit (2) zones

The cutoffs are named rather than written out here because they are recalibrated
whenever the susceptibility map is regenerated; see the constants below for their
current values and the selectivity each one buys.

If rainfall cannot be retrieved the district is reported as
"UNKNOWN (rainfall unavailable)" rather than LOW, because a failed lookup must never
read as "safe".

This is a DECISION-SUPPORT PROTOTYPE, not an official warning system.
Final authority lies with disaster management agencies.
"""

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime
import json
import os
import random
import logging

import numpy as np
import rasterio
from rasterio.warp import transform as rio_transform
from shapely.geometry import shape, Point
import requests

from config import RASTERS, BASE_DIR

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SlipSense.Alerts")

router = APIRouter(prefix="/alerts", tags=["Alert System"])

# =============================================
# CONFIGURATION
# =============================================

DISTRICT_GEOJSON_PATH = BASE_DIR.parent / "Kerala_District_Boundary.geojson"

import rainfall as rainfall_source  # noqa: E402

# Points sampled per district for rainfall; the centroid alone is not representative.
RAINFALL_SAMPLE_POINTS = 5
# A wet fortnight primes slopes even without a single extreme day.
ANTECEDENT_15D_THRESHOLD_MM = 300.0

# Risk thresholds
#
# Recalibrated for the rebuilt v2 susceptibility map by
# ml_models/calibrate_alert_threshold.py. The previous single 0.75 cutoff was tuned
# against the old map, whose values clustered around a median of 0.57; on that map 0.75
# flagged 13% of all terrain while the real landslides sat at a median of only 0.49, so
# it was both noisy and pointed at the wrong ground.
#
# The v2 map is a calibrated probability with a median of 0.044. Cutoffs are now chosen
# by selectivity - the share of terrain each one flags - and checked against how much of
# the 279-point inventory they recover:
#
#   tier        flags % of terrain   cutoff   catches % of real landslides
#   WATCH                     5.0%    0.374                        100.0%
#   HIGH                      1.0%    0.619                         84.9%
#   VERY HIGH                 0.2%    0.869                         32.6%
from thresholds import (SUSCEPTIBILITY_HIGH, SUSCEPTIBILITY_VERY_HIGH,  # noqa: E402
                        SUSCEPTIBILITY_WATCH)

# Share of a district's sampled area that must exceed SUSCEPTIBILITY_HIGH before the
# district counts as exposed. A district *average* is the wrong statistic here: it is
# dominated by the safe majority of terrain and would hide a genuinely dangerous 2%.
DISTRICT_AREA_FRACTION = 0.02

# Retained for the /alerts/status payload and any caller still reading it.
SUSCEPTIBILITY_THRESHOLD = SUSCEPTIBILITY_HIGH
RAINFALL_THRESHOLD_MM = 50.0

# Zone codes from hazard_fused raster
ZONE_FAILURE = 3
ZONE_TRANSIT = 2

# SMS Provider configuration
# Supported: "twilio", "fast2sms", or "vonage"
SMS_PROVIDER = os.environ.get("SMS_PROVIDER", "vonage").lower()

# Twilio configuration (loaded from environment)
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")

# Fast2SMS configuration (FREE for India - 20 SMS/day)
# Register at: https://www.fast2sms.com/
FAST2SMS_API_KEY = os.environ.get("FAST2SMS_API_KEY", "")

# Vonage (Nexmo) configuration - FREE €2 credit, no trial prefix
# Register at: https://dashboard.nexmo.com/sign-up
VONAGE_API_KEY = os.environ.get("VONAGE_API_KEY", "")
VONAGE_API_SECRET = os.environ.get("VONAGE_API_SECRET", "")

# Common configuration
ALERT_RECIPIENTS = os.environ.get("ALERT_RECIPIENTS", "").split(",")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"

# Track sent alerts to prevent duplicates (in-memory, resets on restart)
_sent_alerts: Dict[str, datetime] = {}

# =============================================
# DATA MODELS
# =============================================

class DistrictRiskAssessment(BaseModel):
    district: str
    avg_susceptibility: float
    max_susceptibility: float
    avg_soil_susceptibility: Optional[float] = None
    has_failure_zone: bool
    has_transit_zone: bool
    rainfall_mm: Optional[float] = None
    rainfall_degraded: bool = False
    rainfall_note: Optional[str] = None
    antecedent_15d_mm: Optional[float] = None
    alert_triggered: bool
    risk_level: str  # "VERY HIGH", "HIGH", "MODERATE", "LOW", "UNKNOWN"

class AlertStatus(BaseModel):
    district: str
    alert_sent: bool
    timestamp: Optional[str]
    message: Optional[str]

class AlertResponse(BaseModel):
    districts_checked: int
    alerts_triggered: int
    alerts: List[AlertStatus]
    dry_run: bool

# =============================================
# HELPER FUNCTIONS
# =============================================

def load_districts() -> List[Dict]:
    """Load district boundaries from GeoJSON file."""
    if not DISTRICT_GEOJSON_PATH.exists():
        logger.error(f"District GeoJSON not found: {DISTRICT_GEOJSON_PATH}")
        return []
    
    with open(DISTRICT_GEOJSON_PATH, 'r') as f:
        data = json.load(f)
    
    return data.get("features", [])


def sample_points_in_polygon(polygon_geom, num_points: int = 50) -> List[tuple]:
    """Generate random sample points within a polygon geometry."""
    geom = shape(polygon_geom)
    minx, miny, maxx, maxy = geom.bounds
    
    points = []
    attempts = 0
    max_attempts = num_points * 10
    
    while len(points) < num_points and attempts < max_attempts:
        x = random.uniform(minx, maxx)
        y = random.uniform(miny, maxy)
        point = Point(x, y)
        if geom.contains(point):
            points.append((y, x))  # lat, lon
        attempts += 1
    
    return points


def _to_raster_xy(src, points):
    """Project (lat, lon) pairs into the raster's CRS, dropping any that fall outside."""
    if not points:
        return []
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    if src.crs is not None:
        try:
            xs, ys = rio_transform("EPSG:4326", src.crs, lons, lats)
        except Exception:
            xs, ys = lons, lats
    else:
        xs, ys = lons, lats
    left, bottom, right, top = src.bounds
    return [(x, y) for x, y in zip(xs, ys)
            if left <= x <= right and bottom <= y <= top]


def get_susceptibility_at_points(points: List[tuple]) -> List[float]:
    """Read susceptibility values at given lat/lon points.

    Uses the RandomForest map rather than the CNN map. The CNN raster is produced by
    strided inference and bilinear interpolation, which blurs the sharp hotspots that
    matter for alerting: at a cutoff flagging 5% of terrain it recovered 59% of the
    mapped inventory where the RandomForest map recovered 100%. Regenerating it at a
    finer stride did not help - the smoothing is intrinsic to the CNN's 960 m receptive
    field, not to the sampling. The CNN layer remains available for display.
    """
    values = []

    try:
        with rasterio.open(RASTERS["susceptibility_ml"]) as src:
            # rasterio's sample() walks the points in one pass, reading only the blocks
            # it needs. The previous loop called src.read(1) per point, decompressing the
            # whole 13.4M-cell raster each time - 50 sample points per district across 14
            # districts came to tens of gigabytes of reads for a single /alerts/check.
            for x, y in _to_raster_xy(src, points):
                try:
                    val = float(next(src.sample([(x, y)], 1))[0])
                except (StopIteration, ValueError):
                    continue
                if np.isfinite(val) and val >= 0:  # nodata is negative or NaN
                    values.append(val)
    except Exception as e:
        logger.error(f"Error reading susceptibility raster: {e}")

    return values


def check_hazard_zones_at_points(points: List[tuple]) -> tuple:
    """Check for Failure and Transit zones at given points."""
    has_failure = False
    has_transit = False
    
    try:
        with rasterio.open(RASTERS["hazard_fused"]) as src:
            for x, y in _to_raster_xy(src, points):
                try:
                    zone_code = int(next(src.sample([(x, y)], 1))[0])
                except (StopIteration, ValueError):
                    continue
                if zone_code == ZONE_FAILURE:
                    has_failure = True
                elif zone_code == ZONE_TRANSIT:
                    has_transit = True
    except Exception as e:
        logger.error(f"Error reading hazard raster: {e}")
    
    return has_failure, has_transit


def get_soil_susceptibility_at_points(points: List[tuple]) -> List[float]:
    """Read soil susceptibility index values at given lat/lon points."""
    values = []
    
    try:
        soil_path = RASTERS.get("soil_susceptibility")
        if not soil_path or not os.path.exists(soil_path):
            return values
            
        with rasterio.open(soil_path) as src:
            for x, y in _to_raster_xy(src, points):
                try:
                    val = float(next(src.sample([(x, y)], 1))[0])
                except (StopIteration, ValueError):
                    continue
                if np.isfinite(val) and val > 0 and val != -9999:
                    values.append(val)
    except Exception as e:
        logger.error(f"Error reading soil susceptibility raster: {e}")
    
    return values


def get_rainfall_for_location(lat: float, lon: float) -> float:
    """Removed. Use the `rainfall` module instead.

    The previous implementation reported `rain["1h"] * 24` as a 24-hour total,
    took max() of that against a forecast sum, fetched no antecedent history, and
    returned 0.0 on any API failure - so an unreachable weather service was
    indistinguishable from dry weather and alerts fell silent. It also carried a live
    OpenWeather key as a literal default in source.
    """
    raise NotImplementedError(
        "get_rainfall_for_location has been removed. "
        "Use rainfall.get_rainfall() / rainfall.sample_area(), which return antecedent "
        "windows and raise RainfallUnavailable instead of reporting 0.0 mm."
    )


def get_district_centroid(polygon_geom) -> tuple:
    """Get the centroid of a district polygon."""
    geom = shape(polygon_geom)
    centroid = geom.centroid
    return centroid.y, centroid.x  # lat, lon


def format_sms_message(district: str, rainfall: float) -> str:
    """Format the SMS alert message according to spec."""
    return f"""⚠️ LANDSLIDE ALERT – SlipSense

District: {district}
Risk Level: VERY HIGH
Rainfall: {rainfall:.1f} mm (last 24h)
Soil Condition: Saturated / High clay content

This is an advisory alert.
Follow local authority guidelines."""


def send_twilio_sms(message: str, dry_run: bool = True) -> bool:
    """Send SMS via Twilio API."""
    if dry_run or not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        logger.info(f"[DRY RUN - Twilio] SMS would be sent:\n{message}")
        return True
    
    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        for recipient in ALERT_RECIPIENTS:
            if recipient.strip():
                client.messages.create(
                    body=message,
                    from_=TWILIO_FROM_NUMBER,
                    to=recipient.strip()
                )
                logger.info(f"[ALERT - Twilio] SMS sent to {recipient}")
        
        return True
    except ImportError:
        logger.error("Twilio library not installed. Run: pip install twilio")
        return False
    except Exception as e:
        logger.error(f"Failed to send SMS via Twilio: {e}")
        return False


def send_fast2sms(message: str, dry_run: bool = True) -> bool:
    """
    Send SMS via Fast2SMS API (FREE for India - 20 SMS/day).
    
    Register at https://www.fast2sms.com/ to get your API key.
    This is ideal for prototype/demo purposes.
    """
    if dry_run or not FAST2SMS_API_KEY:
        logger.info(f"[DRY RUN - Fast2SMS] SMS would be sent:\n{message}")
        return True
    
    try:
        url = "https://www.fast2sms.com/dev/bulkV2"
        
        # Clean recipient numbers (remove +91 if present, Fast2SMS expects 10 digits)
        numbers = []
        for recipient in ALERT_RECIPIENTS:
            num = recipient.strip().replace("+91", "").replace("-", "").replace(" ", "")
            if len(num) == 10 and num.isdigit():
                numbers.append(num)
        
        if not numbers:
            logger.error("No valid Indian phone numbers found")
            return False
        
        payload = {
            "route": "q",  # Quick SMS route (free)
            "message": message,
            "flash": 0,
            "numbers": ",".join(numbers)
        }
        
        headers = {
            "authorization": FAST2SMS_API_KEY,
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        if result.get("return"):
            logger.info(f"[ALERT - Fast2SMS] SMS sent to {len(numbers)} recipients")
            return True
        else:
            logger.error(f"Fast2SMS error: {result.get('message', 'Unknown error')}")
            return False
            
    except Exception as e:
        logger.error(f"Failed to send SMS via Fast2SMS: {e}")
        return False


def send_vonage_sms(message: str, dry_run: bool = True) -> bool:
    """
    Send SMS via Vonage (Nexmo) API. FREE €2 credit, no trial prefix.
    Register at https://dashboard.nexmo.com/sign-up
    """
    if dry_run or not VONAGE_API_KEY or not VONAGE_API_SECRET:
        logger.info(f"[DRY RUN - Vonage] SMS would be sent:\n{message}")
        return True
    
    try:
        url = "https://rest.nexmo.com/sms/json"
        
        for recipient in ALERT_RECIPIENTS:
            num = recipient.strip().replace("+", "").replace("-", "").replace(" ", "")
            if not num:
                continue
            
            payload = {
                "from": "SlipSense",
                "text": message,
                "to": num,
                "api_key": VONAGE_API_KEY,
                "api_secret": VONAGE_API_SECRET
            }
            
            response = requests.post(url, json=payload, timeout=10)
            result = response.json()
            
            messages = result.get("messages", [])
            if messages and messages[0].get("status") == "0":
                logger.info(f"[ALERT - Vonage] SMS sent to {recipient}")
            else:
                error_text = messages[0].get("error-text", "Unknown") if messages else "No response"
                logger.error(f"Vonage error for {recipient}: {error_text}")
                return False
        
        return True
    except Exception as e:
        logger.error(f"Failed to send SMS via Vonage: {e}")
        return False


def send_sms(message: str, dry_run: bool = True) -> bool:
    """Send SMS using the configured provider."""
    if SMS_PROVIDER == "twilio":
        return send_twilio_sms(message, dry_run)
    elif SMS_PROVIDER == "vonage":
        return send_vonage_sms(message, dry_run)
    else:  # Default to fast2sms
        return send_fast2sms(message, dry_run)


# =============================================
# API ENDPOINTS
# =============================================

@router.get("/check", response_model=List[DistrictRiskAssessment])
def check_all_districts():
    """
    Check landslide risk for all districts in Kerala.
    Returns risk assessment for each district without triggering alerts.
    """
    districts = load_districts()
    if not districts:
        raise HTTPException(status_code=500, detail="Failed to load district data")
    
    results = []
    
    for feature in districts:
        district_name = feature.get("properties", {}).get("DISTRICT", "Unknown")
        geometry = feature.get("geometry")
        
        if not geometry:
            continue
        
        # Sample points in district
        points = sample_points_in_polygon(geometry, num_points=50)
        
        if not points:
            logger.warning(f"No sample points generated for {district_name}")
            continue
        
        # Get susceptibility values
        sus_values = get_susceptibility_at_points(points)
        avg_sus = sum(sus_values) / len(sus_values) if sus_values else 0.0
        max_sus = max(sus_values) if sus_values else 0.0
        
        # Get soil susceptibility
        soil_values = get_soil_susceptibility_at_points(points)
        avg_soil = sum(soil_values) / len(soil_values) if soil_values else None
        
        # Check hazard zones
        has_failure, has_transit = check_hazard_zones_at_points(points)
        
        # Rainfall, sampled across the district rather than at its centroid: orographic
        # gradients in the Ghats mean one flank can take 200 mm while the centroid stays
        # dry. Alerting follows the wettest sample, not the average.
        rain_degraded = False
        rain_note = None
        try:
            observations = rainfall_source.sample_area(points[:RAINFALL_SAMPLE_POINTS])
            worst = rainfall_source.worst_case(observations)
            rainfall = worst.rain_24h
            antecedent = worst.antecedent_mm
            rain_degraded = worst.degraded or worst.is_stale
            if rain_degraded:
                rain_note = "; ".join(worst.notes) or "stale rainfall data"
        except rainfall_source.RainfallUnavailable as exc:
            # Never substitute 0.0 here. Zero is a real measurement meaning "dry", and
            # treating a failed lookup as dry is what previously let the alert system
            # fall silent whenever the weather API was unreachable.
            logger.error("Rainfall unavailable for %s: %s", district_name, exc)
            rainfall = None
            antecedent = {}
            rain_degraded = True
            rain_note = f"rainfall unavailable: {exc}"
        
        # Determine if alert should trigger
        # Soil susceptibility > 0.6 means clay-rich soil prone to sliding
        #
        # Exposure is the share of sampled points above the HIGH cutoff rather than the
        # district average, which on a calibrated map is pulled down by the safe
        # majority of terrain and never approaches a meaningful threshold.
        exposed_fraction = (
            sum(1 for v in sus_values if v >= SUSCEPTIBILITY_HIGH) / len(sus_values)
            if sus_values else 0.0
        )
        sus_exceeds = (exposed_fraction >= DISTRICT_AREA_FRACTION
                       or max_sus >= SUSCEPTIBILITY_VERY_HIGH)
        has_hazard = has_failure or has_transit
        soil_risky = avg_soil is not None and avg_soil >= 0.6

        # Alert triggers when: high susceptibility + heavy rain + hazard zone
        # Soil data lowers the bar: if soil is risky, rainfall threshold drops to 30mm
        rain_limit = (RAINFALL_THRESHOLD_MM * 0.6) if soil_risky else RAINFALL_THRESHOLD_MM
        # Multi-day saturation is what actually primes these slopes, so a wet fortnight
        # counts even when today alone is unremarkable.
        antecedent_15d = antecedent.get("rain_15d")
        rain_exceeds = (
            rainfall is not None
            and (rainfall >= rain_limit
                 or (antecedent_15d is not None
                     and antecedent_15d >= ANTECEDENT_15D_THRESHOLD_MM))
        )

        alert_triggered = sus_exceeds and rain_exceeds and has_hazard

        # Determine risk level (soil amplifies)
        if rainfall is None:
            # Susceptibility is still known; the trigger side is not. Say so instead of
            # reporting LOW, which would read as "safe".
            risk_level = "UNKNOWN (rainfall unavailable)"
        elif alert_triggered:
            risk_level = "VERY HIGH"
        elif sus_exceeds and has_hazard and soil_risky:
            risk_level = "HIGH"
        elif sus_exceeds and has_hazard:
            risk_level = "HIGH"
        elif sus_exceeds or has_hazard:
            risk_level = "MODERATE"
        else:
            risk_level = "LOW"
        
        results.append(DistrictRiskAssessment(
            district=district_name,
            avg_susceptibility=round(avg_sus, 3),
            max_susceptibility=round(max_sus, 3),
            avg_soil_susceptibility=round(avg_soil, 3) if avg_soil is not None else None,
            has_failure_zone=has_failure,
            has_transit_zone=has_transit,
            rainfall_mm=round(rainfall, 1) if rainfall is not None else None,
            rainfall_degraded=rain_degraded,
            rainfall_note=rain_note,
            antecedent_15d_mm=(round(antecedent_15d, 1)
                               if antecedent_15d is not None else None),
            alert_triggered=alert_triggered,
            risk_level=risk_level
        ))
    
    return results


@router.post("/trigger", response_model=AlertResponse)
def trigger_alerts(dry_run: bool = Query(default=True, description="If true, don't send real SMS")):
    """
    Trigger alert check for all districts and send SMS for high-risk areas.
    
    - **dry_run=true** (default): Log alerts without sending SMS
    - **dry_run=false**: Send real SMS via Twilio (requires credentials)
    """
    assessments = check_all_districts()
    
    alerts_sent = []
    
    for assessment in assessments:
        if assessment.alert_triggered:
            district = assessment.district
            
            # Check if we already sent an alert for this district recently
            if district in _sent_alerts:
                last_sent = _sent_alerts[district]
                hours_since = (datetime.now() - last_sent).total_seconds() / 3600
                if hours_since < 6:  # Don't resend within 6 hours
                    alerts_sent.append(AlertStatus(
                        district=district,
                        alert_sent=False,
                        timestamp=None,
                        message=f"Alert already sent {hours_since:.1f} hours ago"
                    ))
                    continue
            
            # Format and send SMS
            message = format_sms_message(district, assessment.rainfall_mm)
            
            use_dry_run = dry_run or DRY_RUN
            success = send_sms(message, dry_run=use_dry_run)
            
            if success:
                _sent_alerts[district] = datetime.now()
                logger.info(f"[ALERT] SMS {'would be ' if use_dry_run else ''}sent for {district} district")
            
            alerts_sent.append(AlertStatus(
                district=district,
                alert_sent=success,
                timestamp=datetime.now().isoformat() if success else None,
                message="DRY RUN - No SMS sent" if use_dry_run else ("SMS sent successfully" if success else "Failed to send SMS")
            ))
    
    return AlertResponse(
        districts_checked=len(assessments),
        alerts_triggered=len([a for a in alerts_sent if a.alert_sent]),
        alerts=alerts_sent,
        dry_run=dry_run or DRY_RUN
    )


@router.get("/status")
def get_alert_status():
    """
    Get the current alert status for all districts.
    Returns which districts have active alerts and when they were last sent.
    """
    return {
        "sent_alerts": {
            district: timestamp.isoformat()
            for district, timestamp in _sent_alerts.items()
        },
        "sms_provider": SMS_PROVIDER,
        "dry_run_mode": DRY_RUN,
        "twilio_configured": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN),
        "fast2sms_configured": bool(FAST2SMS_API_KEY),
        "recipients_configured": len([r for r in ALERT_RECIPIENTS if r.strip()]),
        "thresholds": {
            "susceptibility": SUSCEPTIBILITY_THRESHOLD,
            "rainfall_mm": RAINFALL_THRESHOLD_MM
        }
    }


@router.get("/test")
def test_alert_system():
    """
    Test the alert system configuration without triggering any alerts.
    Useful for verifying setup.
    """
    districts = load_districts()
    
    return {
        "status": "OK",
        "districts_loaded": len(districts),
        "district_names": [f.get("properties", {}).get("DISTRICT") for f in districts],
        "rasters_configured": {
            "susceptibility_dl": RASTERS.get("susceptibility_dl", "NOT SET"),
            "hazard_fused": RASTERS.get("hazard_fused", "NOT SET"),
        },
        "sms_provider": SMS_PROVIDER,
        "twilio": {
            "account_sid_set": bool(TWILIO_ACCOUNT_SID),
            "auth_token_set": bool(TWILIO_AUTH_TOKEN),
            "from_number_set": bool(TWILIO_FROM_NUMBER),
        },
        "fast2sms": {
            "api_key_set": bool(FAST2SMS_API_KEY),
            "note": "FREE - 20 SMS/day for India. Register at https://www.fast2sms.com/"
        },
        "recipients": len(ALERT_RECIPIENTS) if ALERT_RECIPIENTS != [''] else 0,
        "dry_run_mode": DRY_RUN,
        "thresholds": {
            "susceptibility": SUSCEPTIBILITY_THRESHOLD,
            "rainfall_mm": RAINFALL_THRESHOLD_MM
        }
    }


# =============================================
# SIMULATION ENDPOINT
# =============================================

class SimulationStep(BaseModel):
    step: int
    title: str
    detail: str
    status: str  # "complete", "warning", "danger", "sent"

class SimulationResult(BaseModel):
    district: str
    scenario: str
    simulated_rainfall_mm: float
    simulated_soil_saturation: float
    actual_avg_susceptibility: float
    actual_max_susceptibility: float
    actual_avg_soil_susceptibility: Optional[float]
    has_failure_zone: bool
    has_transit_zone: bool
    risk_level: str
    alert_triggered: bool
    sms_message: str
    sms_sent: bool
    sms_status: str
    recipient: str
    timestamp: str
    steps: List[SimulationStep]


@router.get("/simulate")
def simulate_alert(
    district: str = Query(default="Wayanad", description="District to simulate"),
    rainfall_mm: float = Query(default=180.0, description="Simulated rainfall in mm"),
    soil_saturation: float = Query(default=0.92, description="Simulated soil saturation (0-1)"),
    recipient: str = Query(default="+919207499037", description="Phone number to send SMS to"),
    send_sms_flag: bool = Query(default=False, description="Actually send SMS (false = preview only)")
):
    """
    Run a simulated landslide alert scenario for demo purposes.
    
    Uses REAL susceptibility and soil data from rasters, but SIMULATES
    extreme rainfall conditions to guarantee an alert triggers.
    
    Returns step-by-step animation data for the frontend AlertPanel.
    """
    steps = []
    
    # Step 1: Load district geometry
    districts = load_districts()
    target_feature = None
    for feature in districts:
        name = feature.get("properties", {}).get("DISTRICT", "")
        if name.lower() == district.lower():
            target_feature = feature
            break
    
    if not target_feature:
        # If district not found, use first available
        available = [f.get("properties", {}).get("DISTRICT", "?") for f in districts[:5]]
        raise HTTPException(
            status_code=404, 
            detail=f"District '{district}' not found. Available: {available}"
        )
    
    geometry = target_feature.get("geometry")
    district_name = target_feature["properties"]["DISTRICT"]
    
    steps.append(SimulationStep(
        step=1, title="Scanning District",
        detail=f"Sampling 50 points in {district_name}...",
        status="complete"
    ))
    
    # Step 2: Get REAL susceptibility from raster
    points = sample_points_in_polygon(geometry, num_points=50)
    sus_values = get_susceptibility_at_points(points)
    avg_sus = sum(sus_values) / len(sus_values) if sus_values else 0.0
    max_sus = max(sus_values) if sus_values else 0.0
    
    steps.append(SimulationStep(
        step=2, title="Reading Susceptibility",
        detail=f"Avg: {avg_sus:.3f}, Max: {max_sus:.3f}",
        status="complete" if avg_sus < SUSCEPTIBILITY_THRESHOLD else "warning"
    ))
    
    # Step 3: Get REAL soil data
    soil_values = get_soil_susceptibility_at_points(points)
    avg_soil = sum(soil_values) / len(soil_values) if soil_values else None
    
    steps.append(SimulationStep(
        step=3, title="Soil Analysis",
        detail=f"Avg soil susceptibility: {avg_soil:.3f} — {'Clay-rich, water-retaining' if avg_soil and avg_soil > 0.5 else 'Mixed composition'}" if avg_soil else "No soil data",
        status="warning" if avg_soil and avg_soil > 0.5 else "complete"
    ))
    
    # Step 4: Check hazard zones
    has_failure, has_transit = check_hazard_zones_at_points(points)
    
    steps.append(SimulationStep(
        step=4, title="Checking Hazard Zones",
        detail=f"Failure zones: {'✓ Detected' if has_failure else '✗ None'} | Transit zones: {'✓ Detected' if has_transit else '✗ None'}",
        status="warning" if has_failure else "complete"
    ))
    
    # Step 5: SIMULATED rainfall (this is the trigger)
    steps.append(SimulationStep(
        step=5, title="⚡ Rainfall Surge (Simulated)",
        detail=f"{rainfall_mm:.0f}mm in 24h — EXCEEDS threshold ({RAINFALL_THRESHOLD_MM:.0f}mm) by {rainfall_mm/RAINFALL_THRESHOLD_MM:.1f}×",
        status="danger"
    ))
    
    # Step 6: Soil saturation
    steps.append(SimulationStep(
        step=6, title="🌊 Soil Saturation (Simulated)",
        detail=f"{soil_saturation*100:.0f}% — CRITICAL level. Soil fully saturated, slope stability compromised.",
        status="danger"
    ))
    
    # Step 7: Combined risk calculation
    # Force the risk to be very high (this is a simulation)
    combined_score = min(0.99, avg_sus * 1.3 + 0.2)  # Boost for demo
    risk_level = "VERY HIGH"
    alert_triggered = True
    
    steps.append(SimulationStep(
        step=7, title="🔴 Risk Calculation",
        detail=f"Combined score: {combined_score:.2f} — {risk_level}. Immediate alert required.",
        status="danger"
    ))
    
    # Step 8: Format SMS
    soil_condition = "Saturated" if soil_saturation > 0.8 else "High moisture"
    sms_message = (
        f"[SlipSense ALERT] LANDSLIDE WARNING\n"
        f"District: {district_name}\n"
        f"Risk: {risk_level}\n"
        f"Rainfall: {rainfall_mm:.0f}mm/24h\n"
        f"Soil: {soil_condition} ({soil_saturation*100:.0f}%)\n"
        f"Susceptibility: {max_sus:.2f}\n"
        f"\n"
        f"Avoid slopes, riverbanks & low-lying areas. "
        f"Follow district authority instructions. "
        f"Move to higher ground if in hazard zone."
    )

    # Step 9: Send SMS (or preview)
    sms_sent = False
    sms_status = "Preview only (send_sms=false)"
    
    if send_sms_flag:
        clean_number = recipient.strip().replace("-", "").replace(" ", "")
        # Remove + for Vonage (expects digits only)
        vonage_number = clean_number.replace("+", "")
        
        if VONAGE_API_KEY and VONAGE_API_SECRET:
            try:
                url = "https://rest.nexmo.com/sms/json"
                payload = {
                    "from": "SlipSense",
                    "text": sms_message,
                    "to": vonage_number,
                    "api_key": VONAGE_API_KEY,
                    "api_secret": VONAGE_API_SECRET
                }
                response = requests.post(url, json=payload, timeout=10)
                result = response.json()
                msgs = result.get("messages", [])
                if msgs and msgs[0].get("status") == "0":
                    sms_sent = True
                    sms_status = f"SMS sent to {recipient} via Vonage"
                    logger.info(f"[SIMULATION] SMS sent to {recipient} via Vonage")
                else:
                    error_text = msgs[0].get("error-text", "Unknown") if msgs else "No response"
                    sms_status = f"Vonage error: {error_text}"
                    logger.error(f"[SIMULATION] Vonage error: {result}")
            except Exception as e:
                sms_status = f"Vonage send failed: {str(e)}"
                logger.error(f"[SIMULATION] Vonage error: {e}")
        elif TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
            try:
                from twilio.rest import Client
                client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                msg = client.messages.create(
                    body=sms_message,
                    from_=TWILIO_FROM_NUMBER,
                    to=clean_number
                )
                sms_sent = True
                sms_status = f"SMS sent to {recipient} via Twilio (SID: {msg.sid})"
            except Exception as e:
                sms_status = f"Twilio error: {str(e)}"
        elif FAST2SMS_API_KEY:
            try:
                f2s_number = clean_number.replace("+91", "")
                url = "https://www.fast2sms.com/dev/bulkV2"
                payload = {"route": "q", "message": sms_message, "flash": 0, "numbers": f2s_number}
                headers = {"authorization": FAST2SMS_API_KEY, "Content-Type": "application/json"}
                response = requests.post(url, json=payload, headers=headers, timeout=10)
                result = response.json()
                if result.get("return"):
                    sms_sent = True
                    sms_status = f"SMS sent to {recipient} via Fast2SMS"
                else:
                    sms_status = f"Fast2SMS error: {result.get('message', 'Unknown')}"
            except Exception as e:
                sms_status = f"Fast2SMS error: {str(e)}"
        else:
            sms_status = "No SMS provider configured. Set VONAGE, TWILIO, or FAST2SMS credentials."
    
    steps.append(SimulationStep(
        step=8, title="📱 SMS Alert",
        detail=sms_status,
        status="sent" if sms_sent else "warning"
    ))
    
    return SimulationResult(
        district=district_name,
        scenario=f"Extreme monsoon — {rainfall_mm:.0f}mm rainfall, {soil_saturation*100:.0f}% soil saturation",
        simulated_rainfall_mm=rainfall_mm,
        simulated_soil_saturation=soil_saturation,
        actual_avg_susceptibility=round(avg_sus, 3),
        actual_max_susceptibility=round(max_sus, 3),
        actual_avg_soil_susceptibility=round(avg_soil, 3) if avg_soil else None,
        has_failure_zone=has_failure,
        has_transit_zone=has_transit,
        risk_level=risk_level,
        alert_triggered=alert_triggered,
        sms_message=sms_message,
        sms_sent=sms_sent,
        sms_status=sms_status,
        recipient=recipient,
        timestamp=datetime.now().isoformat(),
        steps=steps
    )

