"""
District-wise Emergency SMS Alert System for SlipSense

This module provides landslide alert functionality that:
1. Analyzes DL susceptibility within each district
2. Checks for hazardous zones (Failure/Transit) in the fused hazard raster
3. Fetches rainfall data from OpenWeather API
4. Sends SMS alerts via Twilio when risk thresholds are exceeded

ALERT TRIGGER CONDITIONS (ALL must be true):
- Average OR maximum DL susceptibility >= 0.75 in the district
- Rainfall >= 50mm in last 24 hours
- District contains Failure (3) or Transit (2) zones

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

# Risk thresholds
SUSCEPTIBILITY_THRESHOLD = 0.75
RAINFALL_THRESHOLD_MM = 50.0

# Zone codes from hazard_fused raster
ZONE_FAILURE = 3
ZONE_TRANSIT = 2

# SMS Provider configuration
# Supported: "twilio" or "fast2sms" (free for India, 20 SMS/day)
SMS_PROVIDER = os.environ.get("SMS_PROVIDER", "fast2sms").lower()

# Twilio configuration (loaded from environment)
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")

# Fast2SMS configuration (FREE for India - 20 SMS/day)
# Register at: https://www.fast2sms.com/
FAST2SMS_API_KEY = os.environ.get("FAST2SMS_API_KEY", "")

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
    has_failure_zone: bool
    has_transit_zone: bool
    rainfall_mm: float
    alert_triggered: bool
    risk_level: str  # "VERY HIGH", "HIGH", "MODERATE", "LOW"

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


def get_susceptibility_at_points(points: List[tuple]) -> List[float]:
    """Read DL susceptibility values at given lat/lon points."""
    values = []
    
    try:
        with rasterio.open(RASTERS["susceptibility_dl"]) as src:
            for lat, lon in points:
                try:
                    # Transform to raster CRS if needed
                    if src.crs is not None:
                        xs, ys = rio_transform("EPSG:4326", src.crs, [lon], [lat])
                        x, y = xs[0], ys[0]
                    else:
                        x, y = lon, lat
                    
                    row, col = src.index(x, y)
                    if 0 <= row < src.height and 0 <= col < src.width:
                        band = src.read(1)
                        val = float(band[row, col])
                        if val >= 0:  # Filter out nodata
                            values.append(val)
                except Exception:
                    continue
    except Exception as e:
        logger.error(f"Error reading susceptibility raster: {e}")
    
    return values


def check_hazard_zones_at_points(points: List[tuple]) -> tuple:
    """Check for Failure and Transit zones at given points."""
    has_failure = False
    has_transit = False
    
    try:
        with rasterio.open(RASTERS["hazard_fused"]) as src:
            for lat, lon in points:
                try:
                    if src.crs is not None:
                        xs, ys = rio_transform("EPSG:4326", src.crs, [lon], [lat])
                        x, y = xs[0], ys[0]
                    else:
                        x, y = lon, lat
                    
                    row, col = src.index(x, y)
                    if 0 <= row < src.height and 0 <= col < src.width:
                        band = src.read(1)
                        zone_code = int(band[row, col])
                        if zone_code == ZONE_FAILURE:
                            has_failure = True
                        elif zone_code == ZONE_TRANSIT:
                            has_transit = True
                except Exception:
                    continue
    except Exception as e:
        logger.error(f"Error reading hazard raster: {e}")
    
    return has_failure, has_transit


def get_rainfall_for_location(lat: float, lon: float) -> float:
    """Fetch rainfall data from OpenWeather API (current + forecast for 24h estimate)."""
    api_key = os.environ.get("OPENWEATHER_API_KEY", "f4b4c6deaacfaacd2060175e4697b694")
    
    # Get current weather rainfall
    current_rain = 0.0
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        current_rain = data.get("rain", {}).get("1h", 0.0) * 24  # Extrapolate to 24h
    except Exception as e:
        logger.warning(f"Error fetching current weather: {e}")
    
    # Also try to get forecast for better 24h estimate
    forecast_rain = 0.0
    try:
        url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}&units=metric&cnt=8"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("list", []):
            forecast_rain += item.get("rain", {}).get("3h", 0.0)
    except Exception as e:
        logger.warning(f"Error fetching forecast: {e}")
    
    return max(current_rain, forecast_rain)


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


def send_sms(message: str, dry_run: bool = True) -> bool:
    """Send SMS using the configured provider."""
    if SMS_PROVIDER == "twilio":
        return send_twilio_sms(message, dry_run)
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
        
        # Check hazard zones
        has_failure, has_transit = check_hazard_zones_at_points(points)
        
        # Get rainfall
        centroid = get_district_centroid(geometry)
        rainfall = get_rainfall_for_location(centroid[0], centroid[1])
        
        # Determine if alert should trigger
        sus_exceeds = avg_sus >= SUSCEPTIBILITY_THRESHOLD or max_sus >= SUSCEPTIBILITY_THRESHOLD
        rain_exceeds = rainfall >= RAINFALL_THRESHOLD_MM
        has_hazard = has_failure or has_transit
        
        alert_triggered = sus_exceeds and rain_exceeds and has_hazard
        
        # Determine risk level
        if alert_triggered:
            risk_level = "VERY HIGH"
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
            has_failure_zone=has_failure,
            has_transit_zone=has_transit,
            rainfall_mm=round(rainfall, 1),
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
