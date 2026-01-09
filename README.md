# SlipSense – Landslide Susceptibility & Runout Prediction System for Kerala

## 1. Project Overview

### 1.1 Problem Statement

Kerala, India, experiences severe landslide events during monsoon seasons due to its unique combination of:
- Steep Western Ghats terrain
- High-intensity rainfall patterns
- Complex drainage networks
- Variable soil and geological conditions

Traditional landslide hazard mapping often relies on coarse-resolution assessments that fail to capture pixel-level terrain variations critical for accurate risk delineation.

### 1.2 Motivation and Objectives

SlipSense was developed to address the need for a **terrain-aware, pixel-level landslide susceptibility and runout prediction system** for Kerala. The primary objectives are:

1. Generate continuous susceptibility probability rasters using machine learning and deep learning models trained on DEM-derived geomorphometric features
2. Predict landslide runout paths using D8 flow direction analysis to identify not only initiation zones but also transit and deposition areas
3. Fuse multiple model outputs into a unified hazard zonation map
4. Provide an interactive web-based GIS interface for visualization and pixel-level inspection
5. Integrate real-time weather data to inform dynamic risk assessment
6. Enable district-wise emergency alert capabilities for decision support

### 1.3 Why Pixel-Level, Terrain-Aware Analysis

Unlike categorical or polygon-based hazard maps, SlipSense provides:
- **Continuous probability values** (0–1) at each raster pixel
- **Terrain-derived features** extracted directly from Digital Elevation Models (DEM)
- **Flow-based runout modeling** that traces the downhill movement path of potential landslides
- **Dynamic risk calculation** integrating susceptibility with real-time rainfall

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SLIPSENSE ARCHITECTURE                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────────┐  │
│  │   DATA SOURCES  │    │   ML/DL MODELS  │    │    GIS PROCESSING       │  │
│  ├─────────────────┤    ├─────────────────┤    ├─────────────────────────┤  │
│  │ • CartoDEM/SRTM │───▶│ • Random Forest │───▶│ • D8 Flow Direction     │  │
│  │ • DEM Derivatives│   │ • U-Net Refiner │    │ • Runout Path Tracing   │  │
│  │ • GSI Historical│    │                 │    │ • Hazard Zone Fusion    │  │
│  │ • District GeoJSON   │                 │    │                         │  │
│  └─────────────────┘    └─────────────────┘    └─────────────────────────┘  │
│           │                      │                        │                 │
│           ▼                      ▼                        ▼                 │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         RASTER OUTPUTS                               │   │
│  │  susceptibility_ml.tif │ susceptibility_dl.tif │ hazard_fused.tif    │   │
│  │  transit_mask.tif │ deposition_mask.tif │ runout_paths.geojson       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                        BACKEND (FastAPI)                             │   │
│  ├──────────────────────────────────────────────────────────────────────┤   │
│  │ • rio-tiler XYZ Tile Service (/tiles/{layer}/{z}/{x}/{y}.png)        │   │
│  │ • Pixel Inspection API (/pixel-info?lat=&lon=)                       │   │
│  │ • Weather Proxy (/weather?lat=&lon=)                                 │   │
│  │ • Alert System (/alerts/check, /alerts/trigger)                      │   │
│  │ • Static File Server (GeoJSON, rasters)                              │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     FRONTEND (React + Vite)                          │   │
│  ├──────────────────────────────────────────────────────────────────────┤   │
│  │ • LeafletJS 2D Map (ESRI Imagery basemap)                            │   │
│  │ • CesiumJS 3D Terrain Viewer (Google Photorealistic Tiles)           │   │
│  │ • Layer Control with Opacity Sliders                                 │   │
│  │ • Legend System                                                      │   │
│  │ • Pixel Inspector (hover + click)                                    │   │
│  │ • Weather Information Display                                        │   │
│  │ • Toast Notifications                                                │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Layer Separation

| Layer | Description | Technologies |
|-------|-------------|--------------|
| **Data Sources** | DEM, derived rasters, historical data, boundaries | GeoTIFF, GeoJSON |
| **ML/DL Models** | Susceptibility prediction and spatial refinement | Random Forest, U-Net |
| **GIS Processing** | Flow direction, runout modeling, hazard fusion | GDAL, rasterio, numpy |
| **Backend APIs** | Tile serving, pixel queries, weather, alerts | FastAPI, rio-tiler, rasterio |
| **Frontend** | Interactive map visualization | React, Leaflet, Cesium, Framer Motion |

---

## 3. Model Architecture and Explanation

### Module 1: Machine Learning Susceptibility Model

**Algorithm**: Random Forest classifier/regressor trained on labeled landslide/non-landslide pixels

**Input Features** (DEM-derived):
| Feature | Description |
|---------|-------------|
| Elevation | Raw DEM values (filled) |
| Slope | Terrain gradient in degrees |
| Aspect | Slope facing direction |
| Flow Accumulation | Upstream contributing area |
| Topographic Wetness Index (TWI) | Soil moisture potential |
| Stream Power Index (SPI) | Erosive power of flowing water |
| Relative Relief | Local elevation range |
| Drainage Density | Stream network intensity |
| Distance to River | Proximity to drainage channels |

**Output**: `susceptibility_ml.tif` – Continuous probability raster (0–1) indicating landslide likelihood at each pixel.

**Interpretation**: Higher values indicate terrain conditions more favorable to landslide initiation based on learned patterns from training data.

---

### Module 2: Deep Learning Spatial Refinement

**Model Type**: U-Net convolutional neural network

**Purpose**: Refine the ML susceptibility output by incorporating spatial context and enforcing coherent boundaries between risk zones.

**Input Channels**:
1. ML susceptibility raster
2. Additional terrain features (slope, TWI, etc.)

**Output**: `susceptibility_dl.tif` – Spatially refined susceptibility raster with improved boundary delineation and noise reduction.

**Rationale**: While the ML model provides pixel-wise predictions, U-Net-based refinement leverages encoder-decoder architecture to capture multi-scale spatial dependencies, producing smoother and more geologically plausible hazard boundaries.

The trained model weights are stored in `backend/rasters/unet_refiner.pth`.

---

### Module 3: D8 Flow Direction & Runout Model

**Algorithm**: D8 (Deterministic 8-neighbor) flow direction

**Process**:
1. **Flow Direction Computation**: For each DEM pixel, determine the direction of steepest descent among 8 neighbors
2. **Flow Accumulation**: Count upstream contributing pixels
3. **Source Identification**: High-susceptibility pixels in failure zones serve as runout starting points
4. **Path Tracing**: Follow flow direction from failure zones downhill until reaching flat terrain or water bodies

**Outputs**:
- `transit_mask.tif` – Raster identifying transit zones (paths of debris movement)
- `deposition_mask.tif` – Raster identifying deposition zones (areas of material accumulation)
- `runout_paths.geojson` – Vector line features representing traced runout trajectories

**Significance**: Runout modeling extends hazard assessment beyond initiation zones to identify downstream areas at risk from debris flow.

---

### Module 4: Fusion & Hazard Zoning

**Process**: Combine outputs from ML, DL, and D8 models into a unified hazard classification.

**Hazard Zone Classification** (stored in `hazard_fused.tif`):

| Code | Zone | Description |
|------|------|-------------|
| 0 | Safe | Low susceptibility, not in runout path |
| 1 | Deposition | Area of debris accumulation |
| 2 | Transit | Path of debris movement |
| 3 | Failure | High susceptibility initiation zone |

**Fusion Logic**:
- Pixels with high DL susceptibility (≥ threshold) are classified as Failure zones
- D8-traced paths overlaying lower susceptibility become Transit zones
- Terminal points of runout paths become Deposition zones

---

## 4. Datasets Used

| Dataset | Source | Resolution | Format | Approx. Size |
|---------|--------|------------|--------|--------------|
| DEM (filled) | CartoDEM / SRTM | 30m | GeoTIFF | ~51 MB |
| Slope | Derived from DEM | 30m | GeoTIFF | ~52 MB |
| Aspect | Derived from DEM | 30m | GeoTIFF | ~52 MB |
| Flow Accumulation | Derived from DEM | 30m | GeoTIFF | ~52 MB |
| TWI (Topographic Wetness Index) | Derived | 30m | GeoTIFF | ~52 MB |
| SPI (Stream Power Index) | Derived | 30m | GeoTIFF | ~52 MB |
| Relative Relief | Derived | 30m | GeoTIFF | ~52 MB |
| Drainage Density | Derived | 30m | GeoTIFF | ~52 MB |
| Distance to River | Derived | 30m | GeoTIFF | ~52 MB |
| Historical Susceptibility | GSI/KSDMA 2022 | Variable | GeoTIFF | ~6 MB |
| District Boundaries | Kerala State | Vector | GeoJSON | ~1.8 MB |
| Historical Landslide Records | KSDMA, Global Catalog | Point data | CSV | ~8 MB |
| Weather Data | OpenWeather API | Real-time | JSON | N/A |

---

## 5. Modules Implemented and Results

| Module | Output | Status | Description |
|--------|--------|--------|-------------|
| ML Susceptibility Model | `susceptibility_ml.tif` | ✅ Completed | Random Forest probability raster |
| DL Spatial Refinement | `susceptibility_dl.tif` | ✅ Completed | U-Net refined susceptibility |
| D8 Runout Model | `runout_paths.geojson`, `transit_mask.tif`, `deposition_mask.tif` | ✅ Completed | Flow-based runout trajectories |
| Hazard Fusion | `hazard_fused.tif` | ✅ Completed | Unified zone classification |
| Backend Tile Server | FastAPI + rio-tiler | ✅ Completed | XYZ tile generation |
| Pixel Inspection API | `/pixel-info` endpoint | ✅ Completed | Query susceptibility at coordinates |
| Weather Integration | `/weather` endpoint | ✅ Completed | OpenWeather API proxy |
| SMS Alert System | `/alerts/*` endpoints | ✅ Completed | District-wise risk alerts |
| Frontend GIS Dashboard | React + Leaflet + Cesium | ✅ Completed | Interactive visualization |

**Qualitative Observations**:
- The DL-refined susceptibility shows improved spatial coherence compared to pixel-wise ML output
- Runout paths follow geologically plausible drainage patterns
- Hazard zones correctly distinguish initiation, transit, and deposition areas
- Real-time weather integration provides dynamic risk context

---

## 6. Frontend Architecture

### 6.1 Base Map
- **Provider**: ESRI World Imagery via ArcGIS REST services
- **Library**: LeafletJS with react-leaflet bindings

### 6.2 Raster Tile Overlays
The following layers are served as XYZ tiles via the backend:

| Layer Key | Display Name | Description |
|-----------|--------------|-------------|
| `susceptibilityML` | ML Susceptibility | Raw ML probability output |
| `susceptibilityDL` | DL Refined Susceptibility | U-Net refined output |
| `historicalSusceptibility` | GSI Historical | KSDMA/GSI 2022 data |
| `hazardFused` | Final Hazard Map | Fused zone classification |
| `transit` | Transit Zone | Movement path mask |
| `deposition` | Deposition Zone | Accumulation area mask |

### 6.3 Vector Overlays
- **Runout Paths**: GeoJSON line features with interactive hover/click
- **District Boundaries**: Kerala district polygons (selectable filter)

### 6.4 Interactive Features
| Feature | Description |
|---------|-------------|
| Layer Toggle | Enable/disable individual layers |
| Opacity Sliders | Adjust transparency per layer |
| Pixel Inspector (Click) | Query backend for susceptibility, zone, and risk at clicked location |
| Pixel Inspector (Hover) | Real-time tooltip with zone and susceptibility values |
| Weather Display | Current temperature, humidity, rainfall at location |
| 3D Terrain View | Cesium modal with Google Photorealistic 3D Tiles |
| Toast Notifications | User feedback for layer changes and data loading |
| Legend Panel | Color coding for zones and susceptibility gradient |

### 6.5 District Filter
For historical susceptibility layer, users can filter by individual Kerala districts to view district-specific GSI data.

---

## 7. Backend Architecture

### 7.1 FastAPI Service

**Entry Point**: `backend/app.py`

**Endpoints**:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/tiles/{layer}/{z}/{x}/{y}.png` | GET | XYZ tile for specified layer |
| `/pixel-info` | GET | Query susceptibility and zone at lat/lon |
| `/weather` | GET | Proxy to OpenWeather API |
| `/alerts/check` | GET | Check risk levels for all districts |
| `/alerts/trigger` | POST | Trigger SMS alerts for high-risk districts |
| `/alerts/status` | GET | View sent alerts and configuration |
| `/alerts/test` | GET | Test alert system configuration |
| `/rasters/*` | Static | Serve GeoJSON and static files |

### 7.2 Tile Generation (rio-tiler)

The tile service uses `rio-tiler` with `COGReader` to generate PNG tiles from Cloud-Optimized GeoTIFFs on-the-fly:

- Single-band rasters are normalized to 0–255 grayscale
- Multi-class hazard raster uses custom colorization:
  - Failure (3): Red `#dc2626`
  - Transit (2): Orange `#ffa500`
  - Deposition (1): Yellow `#ffff00`
  - Safe (0): Transparent/Black
- Historical susceptibility uses RGBA with transparency for NoData

### 7.3 Pixel Inspection API

`/pixel-info?lat={lat}&lon={lon}` returns:
```json
{
  "latitude": 12.5,
  "longitude": 75.0,
  "zone": "Failure|Transit|Deposition|Safe",
  "susceptibility": 0.782,
  "historical_susceptibility": 4,
  "historical_risk_class": "High|Moderate|Low",
  "rainfall": 2.5,
  "riskLevel": "High|Moderate|Low"
}
```

Risk level is computed as: `susceptibility × (1 + rainfall/20)`

### 7.4 SMS Alert System

**Trigger Conditions** (all must be true):
1. Average OR maximum DL susceptibility ≥ 0.75 in district
2. Rainfall ≥ 50mm in last 24 hours
3. District contains Failure or Transit zones

**Providers Supported**:
- Twilio (international)
- Fast2SMS (free tier for India, 20 SMS/day)

**Configuration** (via environment variables):
- `SMS_PROVIDER`: "twilio" or "fast2sms"
- `DRY_RUN`: "true" to log without sending
- `ALERT_RECIPIENTS`: Comma-separated phone numbers

---

## 8. Project Limitations

1. **DEM Resolution Dependency**: Results are constrained by 30m SRTM/CartoDEM resolution; sub-meter terrain features are not captured

2. **Rainfall Threshold Assumptions**: The 50mm/24hr threshold is a heuristic; actual triggering rainfall varies by geology and antecedent moisture

3. **Advisory Nature**: Outputs are for decision-support only; final authority lies with official disaster management agencies (KSDMA, NDMA)

4. **District-Level Aggregation**: Alert system aggregates at district level; panchayat-level granularity is not currently supported

5. **Static Training Data**: Models are trained on historical events; emerging patterns from climate change may not be fully captured

6. **Network Dependency**: Weather integration and alerts require internet connectivity

7. **Validation Scope**: Model outputs have not undergone formal field validation with ground-truth surveys

---

## 9. Future Scope

1. **Higher-Resolution DEM**: Integrate LiDAR or 10m DEM for improved micro-terrain analysis

2. **Real-Time Rainfall Ingestion**: Connect to IMD AWS network for continuous rainfall monitoring

3. **Mobile Alert Integration**: Push notifications via mobile apps in addition to SMS

4. **Panchayat-Level Zoning**: Downscale alerts and analysis to local administrative units

5. **Temporal Landslide Forecasting**: Incorporate antecedent rainfall indices and soil moisture for time-dependent predictions

6. **Field Validation**: Systematic ground-truth surveys at predicted high-risk locations

7. **Multi-Hazard Integration**: Combine with flood and earthquake susceptibility for comprehensive risk assessment

8. **User Feedback Loop**: Allow local authorities to report events and improve model training

---

## 10. References

- Geological Survey of India (GSI) Landslide Susceptibility Maps
- Kerala State Disaster Management Authority (KSDMA) Data
- CartoDEM / SRTM Digital Elevation Models
- OpenWeather API Documentation
- rio-tiler Documentation
- Leaflet and CesiumJS Documentation

---

## License

This project is developed as an academic final-year project. It is intended for educational and research purposes. For any operational use, proper authorization from relevant authorities is required.

---

*SlipSense – A terrain-aware approach to landslide hazard assessment for Kerala*
