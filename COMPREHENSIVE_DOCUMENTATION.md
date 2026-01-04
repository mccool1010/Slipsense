# SLIPSENSE - Comprehensive Documentation

## Table of Contents
1. [Project Overview](#project-overview)
2. [System Architecture](#system-architecture)
3. [Directory Structure & File Descriptions](#directory-structure--file-descriptions)
4. [Backend Components](#backend-components)
5. [Frontend Components](#frontend-components)
6. [ML Models & Data Pipeline](#ml-models--data-pipeline)
7. [Packages & Dependencies](#packages--dependencies)
8. [How Everything Works Together](#how-everything-works-together)
9. [Running the Application](#running-the-application)

---

## Project Overview

**SlipSense** is a comprehensive **Landslide Susceptibility & Runout Prediction System** that combines machine learning, deep learning, and geospatial analysis to:

- **Predict landslide-prone areas** using ML and DL models
- **Calculate hazard zones** (failure, transit, deposition)
- **Generate runout paths** using D8 flow direction algorithm
- **Provide real-time risk assessment** with weather integration
- **Visualize predictions** on an interactive map with overlay layers

The system is designed for regions like Kerala with high landslide risk, integrating topographic data, meteorological information, and trained ML/DL models to provide actionable hazard maps.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   SLIPSENSE SYSTEM                      │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │         FRONTEND (React + Leaflet + Vite)        │  │
│  │  - Interactive map with layer controls           │  │
│  │  - Real-time hazard visualization                │  │
│  │  - Risk information display                       │  │
│  │  - 3D terrain view (Cesium integration for visual)
│  │    - Uses `Cesium` package and a `CesiumView.jsx` component
│  │    - Module-level Ion token initialization (set on module load)
│  │    - Asset path configured via `CESIUM_BASE_URL` for workers/widgets
│  │    - Vite config updated to include and optimize `cesium` during dev/build
│  └──────────────────────────────────────────────────┘  │
│                        ↓ (HTTP)                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │     BACKEND (FastAPI + Rio-Tiler + Rasterio)    │  │
│  │  - Tile generation for map layers                │  │
│  │  - Pixel-level hazard information                │  │
│  │  - Weather data integration                       │  │
│  │  - Risk calculation API                           │  │
│  └──────────────────────────────────────────────────┘  │
│                        ↓ (File I/O)                     │
│  ┌──────────────────────────────────────────────────┐  │
│  │   ML MODELS & GEOSPATIAL DATA PROCESSING        │  │
│  │  - XGBoost ML model (susceptibility)              │  │
│  │  - Deep Learning U-Net model (refinement)         │  │
│  │  - D8 flow routing (runout paths)                 │  │
│  │  - Hazard fusion (multi-zone integration)         │  │
│  └──────────────────────────────────────────────────┘  │
│                        ↓ (GeoTIFF/GeoJSON)              │
│  ┌──────────────────────────────────────────────────┐  │
│  │      GEOSPATIAL DATA & RASTER LAYERS            │  │
│  │  - DEM, Slope, Aspect, Flow Accumulation         │  │
│  │  - Susceptibility maps (ML & DL)                  │  │
│  │  - Hazard fusion maps (merged predictions)        │  │
│  │  - Runout paths (GeoJSON)                         │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## Directory Structure & File Descriptions

### Root Level
```
c:\coding\Slipsense\
├── README.md                  - Original project README (minimal)
├── run-all.bat               - Master startup script (launches both backend & frontend)
├── run-backend.bat           - Backend startup script
├── run-frontend.bat          - Frontend startup script
├── backend/                  - FastAPI server for tile serving & API
├── frontend/                 - React+Vite UI for map visualization
├── ml_models/                - ML/DL model training & inference scripts
├── data/                     - Training datasets (CSV files)
└── models/                   - Model definitions & utilities
```

### `/backend` - FastAPI Tile Server
```
backend/
├── app.py                    - Main FastAPI application entry point
├── config.py                 - Configuration (raster file paths)
├── tiles.py                  - Tile generation & colorization logic
├── pixel.py                  - Pixel-level data query & risk calculation
├── requirements.txt          - Python dependencies for backend
├── .venv/                    - Virtual environment (if created)
└── rasters/                  - Geospatial data files
    ├── susceptibility_ml.tif      - ML model predictions
    ├── susceptibility_dl.tif      - DL model refined predictions
    ├── hazard_fused.tif           - Final merged hazard map
    ├── transit_mask.tif           - Transit zone raster
    ├── deposition_mask.tif        - Deposition zone raster
    ├── runout_paths.geojson       - Flow paths as GeoJSON
    ├── DEM_filled_75.tif          - Digital Elevation Model
    ├── slope75.tif                - Slope (degrees)
    ├── Flow_Accumulation*.tif     - Drainage accumulation
    ├── Relative_Relief_75.tif     - Relative elevation
    ├── Distance_to_River_75.tif   - Distance from rivers
    ├── Drainage_Density_Final.tif - Drainage network density
    ├── SPI75.tif                  - Stream Power Index
    └── unet_refiner.pth           - Deep learning model weights
```

**Key Files Explained:**

| File | Purpose | Technology |
|------|---------|-----------|
| `app.py` | FastAPI application with CORS, routers, and static file serving | FastAPI framework |
| `tiles.py` | Generates map tiles from rasters with colorization for hazard visualization | Rio-Tiler, Rasterio |
| `pixel.py` | Returns hazard info for specific coordinates; integrates weather data | OpenWeather API |
| `config.py` | Maps logical layer names to file paths | Python pathlib |
| `requirements.txt` | Backend dependencies: fastapi, uvicorn, rio-tiler, rasterio, Pillow | pip |

### `/frontend` - React+Vite Web Application
```
frontend/
├── package.json              - Node.js dependencies & scripts
├── index.html                - HTML entry point
├── vite.config.js            - Vite build configuration
├── eslint.config.js          - ESLint rules
├── src/
│   ├── main.jsx              - React app bootstrap
│   ├── App.jsx               - Main app component (state management)
│   ├── App.css               - Global styling
│   ├── index.css             - Base CSS
│   ├── components/
│   │   ├── MapView.jsx       - Leaflet map with layer rendering
│   │   ├── CesiumView.jsx    - Cesium 3D viewer component (optional)
│   │   ├── LayerControl.jsx  - Toggle & opacity controls
│   │   └── Legend.jsx        - Color legend for hazard zones
│   └── assets/               - Images, icons, etc.
└── public/                   - Static assets
```

**Key Files Explained:**

| File | Purpose | Technology |
|------|---------|-----------|
| `App.jsx` | Root component managing global state (active layers, opacity, selected point) | React 19 |
| `MapView.jsx` | Renders interactive map with tile layers and GeoJSON; handles click/hover | React-Leaflet 5 |
| `CesiumView.jsx` | 3D viewer using the `cesium` package — handles token, asset path, and optional 3D tiles | Cesium JS |
| `LayerControl.jsx` | Checkboxes to toggle layers and sliders to adjust opacity | React |
| `Legend.jsx` | Visual guide showing color codes for hazard zones | React |
| `package.json` | Dependencies: React, React-DOM, Leaflet, React-Leaflet, Cesium (optional), Tailwind, Vite | npm |

### `/ml_models` - Model Training & Inference
```
ml_models/
├── train_models.py           - XGBoost model training on historical data
├── generate_susceptibility_map.py - Applies ML model to raster data
├── generate_runout_and_fuse.py - D8 routing, zone creation, hazard fusion
├── unet_refine.py            - Deep learning refinement (U-Net)
├── colorize_hazard.py        - Hazard map colorization helper
├── test_susceptibility.py     - Model validation script
├── test.py                    - Generic testing utilities
├── requirements.txt           - ML dependencies
├── my_venv_3_12/             - Virtual environment with all packages
└── [other utilities]
```

**Key Scripts Explained:**

| Script | Input | Output | Purpose |
|--------|-------|--------|---------|
| `train_models.py` | CSV landslide occurrence data | `landslide_model_xgb.pkl` | Train XGBoost binary classifier on historical data |
| `generate_susceptibility_map.py` | Raster features + trained model | `susceptibility_ml.tif` | Apply ML model across entire study region |
| `generate_runout_and_fuse.py` | DL susceptibility, DEM, slope | Hazard masks + GeoJSON | Calculate runout paths and fuse zones |
| `unet_refine.py` | ML susceptibility map | `susceptibility_dl.tif` | Refine predictions using deep learning |

### `/data` - Training Datasets
```
data/
├── Global_Landslide_Catalog_Export_rows.csv  - Global landslide database
├── kerala_flood_data.csv                     - Regional flood information
├── kerala_landslide_data.csv                 - Regional landslide records
└── landslide - Sheet1 (1).csv                - Training dataset for ML model
```

### `/models` - Model Utilities
```
models/
├── dem.py                    - Digital Elevation Model utilities
└── [other model helpers]
```

---

## Backend Components

### 1. **app.py** - Main FastAPI Application

```python
# CORS Middleware: Allows frontend to communicate with backend
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)

# Routers: Include tile and pixel information endpoints
app.include_router(tiles_router)    # Endpoints: /tiles/{layer}/{z}/{x}/{y}.png
app.include_router(pixel_router)    # Endpoints: /pixel-info?lat={lat}&lon={lon}

# Static Files: Serve raster data directly
app.mount("/rasters", StaticFiles(...))
```

**What it does:**
- Creates REST API for frontend to query
- Enables cross-origin requests
- Serves pre-processed raster files

### 2. **tiles.py** - Map Tile Generation

**Key Functions:**

```python
def _normalize_band(band):
    # Normalizes single band (0-255) for display
    # Formula: (value - min) / (max - min) * 255
    
def _normalize_rgb(arr):
    # Normalizes each band independently in RGB image
    
def colorize_hazard(arr):
    # Maps hazard codes to colors:
    # 0 = Safe (black)
    # 1 = Deposition (yellow RGB: 255,255,0)
    # 2 = Transit (orange RGB: 255,165,0)
    # 3 = Failure (red RGB: 220,38,38)
```

**Endpoint:** `GET /tiles/{layer}/{z}/{x}/{y}.png`

**Process:**
1. Receives tile request with zoom level (z), tile coordinates (x, y)
2. Uses rio-tiler's COGReader to read Cloud-Optimized GeoTIFF
3. Extracts data from specified region
4. Normalizes values to 0-255 range
5. Special handling for hazard_fused (categorical colorization)
6. Returns PNG image for map overlay

**Layers Supported:**
- `susceptibility_ml` - ML model predictions (grayscale)
- `susceptibility_dl` - DL refined predictions (grayscale)
- `hazard_fused` - Final hazard zones (colored: red/orange/yellow)
- `transit` - Transit zone mask
- `deposition` - Deposition zone mask

### 3. **pixel.py** - Hazard Information API

**Endpoint:** `GET /pixel-info?lat={latitude}&lon={longitude}`

**Process:**

```python
# 1. Coordinate Transformation
# Convert WGS84 (lat/lon) to raster coordinates using geospatial metadata

# 2. Read Rasters at Pixel Location
# - susceptibility_dl: Get predicted landslide probability (0-1)
# - hazard_fused: Get zone code (0-3)

# 3. Fetch Weather Data
rainfall_at(lat, lon):
    # OpenWeather API call
    # Returns 1-hour rainfall (mm)

# 4. Calculate Risk
risk_val = susceptibility * (1 + rainfall / 20)
# Higher rainfall → higher risk
# Risk levels: Low (<0.4), Moderate (0.4-0.7), High (>0.7)

# 5. Return JSON Response
{
    "latitude": float,
    "longitude": float,
    "zone": string,              # "Safe", "Deposition", "Transit", "Failure"
    "susceptibility": float,     # 0.0-1.0
    "rainfall": float,           # mm/hr
    "riskLevel": string          # "Low", "Moderate", "High"
}
```

**Zone Mapping:**
| Code | Zone | Meaning |
|------|------|---------|
| 0 | Safe | Low/no hazard |
| 1 | Deposition | Material accumulation area |
| 2 | Transit | Landslide flow path |
| 3 | Failure | Initiation zone (highest risk) |

### 4. **config.py** - File Path Configuration

Maps logical layer names to actual file paths on disk:

```python
RASTERS = {
    "susceptibility_ml": "susceptibility_ml.tif",
    "susceptibility_dl": "susceptibility_dl.tif",
    "hazard_fused": "hazard_fused.tif",
    "transit": "transit_mask.tif",
    "deposition": "deposition_mask.tif",
}
```

---

## Frontend Components

### 1. **App.jsx** - Main Application Component

**Global State Management:**

```javascript
// Layer visibility toggles
activeLayers: {
    susceptibilityML: false,
    susceptibilityDL: true,
    hazardFused: true,
    runout: true,
    transit: false,
    deposition: false
}

// Layer transparency (0-1)
layerOpacity: {
    susceptibilityML: 0.6,
    susceptibilityDL: 0.7,
    hazardFused: 0.8,
    ...
}

// Selected location data
selectedPoint: {
    lat: float,
    lon: float,
    zone: string,
    susceptibility: float,
    rainfall: float,
    riskLevel: string
}
```

**Event Handlers:**

| Handler | Trigger | Action |
|---------|---------|--------|
| `toggleLayer()` | Checkbox click | Show/hide layer |
| `changeOpacity()` | Slider move | Adjust transparency |
| `handleMapClick()` | Map click | Query /pixel-info API |
| `open3DView()` | "View 3D" button | Open Cesium viewer |

**Notes about the 3D viewer (`CesiumView.jsx`):**

- `CesiumView.jsx` initializes `Cesium.Ion.defaultAccessToken` at module load so Ion methods are callable when the viewer is created.
- `window.CESIUM_BASE_URL` is set to point Cesium to its static asset directory (workers, widgets, assets) so the dev server and production build can serve them.
- `vite.config.js` was updated to include `optimizeDeps.include = ['cesium']` and to allow filesystem access for local Cesium assets during development.
- The component mounts the Cesium `Viewer` only once (protects against React 18 strict-mode double-mount), cleans up on unmount, and uses a graceful fallback to OpenStreetMap imagery when Ion imagery or 3D tiles are unavailable.
- An optional Cesium Ion 3D tileset (Google Photorealistic) is attempted using asset id `2275207`; the code logs and continues if the tileset cannot be fetched or returns 404/403 from Ion.

### 2. **MapView.jsx** - Interactive Map

**Technology:** React-Leaflet (wrapper around Leaflet.js)

**Features:**

```javascript
// Base map tiles (OpenStreetMap)
<TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />

// Hazard raster overlays
<TileLayer url="http://localhost:8000/tiles/{layer}/{z}/{x}/{y}.png" />

// Runout paths GeoJSON
<GeoJSON data={runoutGeoJSON} style={{color: 'blue'}} />

// Interactive handlers
<MapClickHandler onMapClick={handleMapClick} />
<MapHoverHandler onHover={handleHover} />
```

**Click Handler:**
- User clicks on map
- Sends `lat`, `lon` to parent component
- Parent fetches `/pixel-info` from backend
- Results displayed in side panel

**Hover Handler:**
- Tracks mouse position
- After 500ms delay, fetches pixel data
- Shows tooltip with susceptibility/rainfall/risk

### 3. **LayerControl.jsx** - Layer Toggles & Opacity

**UI Elements:**

```jsx
// For each layer:
<input type="checkbox" /> {layer name}
{layerActive && <input type="range" min="0" max="1" />}
```

**Layers Available:**
1. **ML Susceptibility** - Machine learning model predictions
2. **DL Refined Susceptibility** - Deep learning refined model
3. **Final Hazard Map** - Merged multi-zone predictions
4. **Runout Paths** - GeoJSON flow lines
5. **Transit Zone** - Material transit area
6. **Deposition Zone** - Material accumulation area

### 4. **Legend.jsx** - Color Legend

**Color Scheme:**

```
Failure Zone (Red)        → RGB(220, 38, 38)   → High risk initiation
Transit Zone (Orange)     → RGB(255, 165, 0)   → Medium risk flow path
Deposition Zone (Yellow)  → RGB(255, 255, 0)   → Lower risk accumulation
Susceptibility Gradient   → Grayscale 0-255    → Probability intensity
```

---

## ML Models & Data Pipeline

### 1. **XGBoost Machine Learning Model** (`train_models.py`)

**Purpose:** Predict landslide susceptibility from geospatial features

**Training Data:**
- Source: `data/landslide - Sheet1 (1).csv`
- Features: Topographic variables (slope, aspect, DEM, flow accumulation, etc.)
- Target: Binary classification (landslide = 1, safe = 0)

**Model Configuration:**

```python
XGBClassifier(
    n_estimators=500,           # 500 decision trees
    learning_rate=0.05,         # Slow learning for stability
    max_depth=6,                # Tree depth (avoid overfitting)
    subsample=0.8,              # 80% row sampling
    colsample_bytree=0.7,       # 70% feature sampling
    objective='binary:logistic', # Binary classification
    scale_pos_weight=imbalance_ratio  # Weights minority class
)
```

**Class Imbalance Handling:**
- Landslides are rare (imbalanced dataset)
- `scale_pos_weight` automatically adjusts loss for minority class
- Formula: `weight = count(class_0) / count(class_1)`

**Output:** `landslide_model_xgb.pkl` (pickled model for inference)

### 2. **Susceptibility Map Generation** (`generate_susceptibility_map.py`)

**Workflow:**

```
Input Rasters:
├── Relative_Relief_75.tif
├── SPI75.tif (Stream Power Index)
├── TWI_FINAL.tif (Topographic Wetness Index)
├── Flow_Accumulation_clean75.tif
├── aspect75.tif
├── slope75.tif
├── DEM_filled_75.tif
├── Distance_to_River_75.tif
└── Drainage_Density_Final.tif
    ↓
[Stack 9 rasters into 3D array]
    ↓
[Reshape to 2D: rows × 9 features]
    ↓
[Load trained XGBoost model]
    ↓
[model.predict_proba() → probabilities]
    ↓
Output: susceptibility_ml.tif
(Float32 raster, values 0.0-1.0)
```

**Preprocessing:**
- Handles missing data (NaN) by replacing with band mean
- Resizes mismatched rasters using bilinear interpolation
- Normalizes to common grid

### 3. **Deep Learning Refinement** (`unet_refine.py`)

**Purpose:** Refine ML predictions using U-Net architecture

**Model:** U-Net (Convolutional encoder-decoder)
- Input: ML susceptibility map (grayscale)
- Output: Refined susceptibility map
- Architecture: Captures local patterns for improvement

**File:** `unet_refiner.pth` (PyTorch model weights)

**Process:**
```
ML Susceptibility
    ↓
U-Net Model (trained on improved data)
    ↓
DL Refined Susceptibility (higher accuracy)
```

### 4. **Runout Path Generation & Hazard Fusion** (`generate_runout_and_fuse.py`)

**Purpose:** Model landslide flow direction and create multi-zone hazard map

**Step 1: D8 Flow Direction Calculation**

D8 (deterministic 8-point) algorithm:
- For each pixel, finds steepest downslope neighbor
- Encodes direction as bitmask (1=E, 2=SE, 4=S, 8=SW, 16=W, 32=NW, 64=N, 128=NE)
- Based on DEM elevation differences

```python
# For each pixel, find neighbor with max slope
max_slope = 0
for each 8 neighbor:
    slope = (current_elevation - neighbor_elevation) / distance
    if slope > max_slope:
        best_direction = bitmask
```

**Step 2: Runout Path Tracing**

```
For each high-susceptibility pixel:
    ├── Start at centroid of source zone
    ├── Follow D8 direction downslope
    ├── Stop when reaching stream (flow_acc > threshold)
    ├── Record path as (lon, lat) coordinates
    └── Save as GeoJSON LineString
```

**Output:** `runout_paths.geojson` - MultiLineString features

**Step 3: Zone Creation**

```python
# Identify 3 hazard zones:

# 1. FAILURE ZONE (Initiation)
failure_zone = (susceptibility >= 0.25)

# 2. TRANSIT ZONE (Flow path)
runout_mask = rasterize(runout_lines)
transit_zone = dilate(runout_mask, buffer_radius=5)

# 3. DEPOSITION ZONE (Accumulation)
deposition_zone = (flow_acc > STREAM_ACC_THRESH * 2) & (slope <= 15°)
```

**Step 4: Hazard Fusion (Priority-based)**

```python
# Assign codes based on zone membership (priority: failure > transit > deposition)

fused = 0  # Default: safe
fused[susceptibility >= 0.25] = 3          # Failure (red)
fused[(transit==1) & (fused==0)] = 2       # Transit (orange)
fused[(deposition==1) & (fused==0)] = 1    # Deposition (yellow)
```

**Output:** `hazard_fused.tif` - Categorical raster (codes 0-3)

---

## Packages & Dependencies

### Backend (`backend/requirements.txt`)

| Package | Version | Purpose |
|---------|---------|---------|
| **fastapi** | Latest | Web framework for building REST APIs |
| **uvicorn[standard]** | Latest | ASGI server to run FastAPI app |
| **rio-tiler** | Latest | Reads Cloud-Optimized GeoTIFFs and generates tiles |
| **rasterio** | Latest | Reads/writes geospatial raster data |
| **Pillow** | Latest | Image processing (PNG encoding) |

**Why These?**
- **FastAPI**: Modern, fast, type-checked Python web framework
- **rio-tiler**: Specialized for geospatial tile serving without loading entire raster
- **Rasterio**: GDAL wrapper for precise geospatial I/O
- **Pillow**: Simple, reliable image format conversion

### ML Models (`ml_models/requirements.txt`)

| Package | Version | Purpose |
|---------|---------|---------|
| **numpy** | 2.2.6 | Numerical computing, array operations |
| **scipy** | 1.16.3 | Scientific computing (interpolation, NDimage ops) |
| **pandas** | 2.3.3 | Data manipulation (CSV loading, feature engineering) |
| **scikit-learn** | 1.7.2 | ML utilities (train-test split, metrics) |
| **xgboost** | Latest | Gradient boosting classifier |
| **torch** | 2.9.1 | Deep learning framework (U-Net) |
| **rasterio** | 1.3.10 | Geospatial raster I/O |
| **Shapely** | Latest | Geometric operations (LineString creation) |
| **opencv-python** | 4.12.0.88 | Image processing |
| **matplotlib** | 3.10.7 | Visualization |
| **joblib** | 1.5.2 | Model serialization |
| **requests** | 2.32.5 | HTTP requests (OpenWeather API) |

**Why Key Libraries?**
- **XGBoost**: State-of-the-art gradient boosting; handles imbalanced classification well
- **PyTorch**: Deep learning framework for U-Net architecture
- **Rasterio/Shapely**: Standard tools for geospatial data processing
- **Joblib**: Efficient model pickling for large ML models

### Frontend (`frontend/package.json`)

| Package | Version | Purpose |
|---------|---------|---------|
| **react** | 19.1.0 | UI component framework |
| **react-dom** | 19.1.0 | React browser rendering |
| **leaflet** | 1.9.4 | Map rendering library |
| **react-leaflet** | 5.0.0 | React wrapper for Leaflet |
| **vite** | 7.0.0 | Build tool (dev server + bundler) |
| **tailwindcss** | 4.1.11 | Utility CSS framework |
| **eslint** | 9.29.0 | Code quality linter |

**Dev Tools:**
- **@vitejs/plugin-react**: Fast refresh for development
- **autoprefixer**: Browser compatibility for CSS
- **postcss**: CSS processing pipeline

**Why These?**
- **React**: Industry-standard UI library with component reusability
- **Leaflet**: Lightweight, battle-tested mapping library
- **react-leaflet**: Clean React integration with Leaflet
- **Vite**: Fast, modern build tool (10x faster than Webpack)
- **Tailwind**: Rapid styling without custom CSS

---

## How Everything Works Together

### Complete User Interaction Flow

```
1. USER OPENS BROWSER (localhost:5173)
   ↓
2. FRONTEND (React) LOADS
   ├── Initializes state (active layers, opacity, selected point)
   ├── Fetches runout_paths.geojson from backend
   └── Renders Leaflet map with OSM base layer
   ↓
3. USER CLICKS "Enable Hazard Map"
   ├── toggleLayer() updates state
   ├── MapView re-renders with hazard_fused tile layer
   └── Tile requests sent to backend: GET /tiles/hazard_fused/{z}/{x}/{y}.png
   ↓
4. BACKEND TILE REQUEST
   ├── tiles.py receives request
   ├── Opens hazard_fused.tif with rio-tiler
   ├── Reads tile region
   ├── Applies colorization (3=red, 2=orange, 1=yellow, 0=black)
   ├── Encodes as PNG
   └── Returns image to frontend
   ↓
5. FRONTEND DISPLAYS TILE
   ├── Leaflet renders PNG on map
   ├── User sees colored hazard zones
   └── Can adjust opacity with slider
   ↓
6. USER CLICKS ON MAP LOCATION
   ├── MapClickHandler captures coordinates (lat, lon)
   ├── Sends to parent: handleMapClick({lat, lon})
   ├── Fetch request to: GET /pixel-info?lat={lat}&lon={lon}
   ↓
7. BACKEND PIXEL INFO REQUEST
   ├── pixel.py receives coordinates
   ├── Reads susceptibility_dl.tif at pixel location
   ├── Reads hazard_fused.tif at pixel location
   ├── Transforms WGS84 → raster CRS
   ├── Extracts values at (row, col)
   ├── Calls OpenWeather API for rainfall
   ├── Calculates risk: risk = susceptibility × (1 + rainfall/20)
   ├── Maps zone code to zone name
   └── Returns JSON response
   ↓
8. FRONTEND DISPLAYS RESULTS
   ├── Sets selectedPoint state with response data
   ├── Side panel shows:
   │   ├── Latitude, Longitude
   │   ├── Zone: "Failure", "Transit", "Deposition", or "Safe"
   │   ├── Susceptibility: 0.0-1.0 (probability)
   │   ├── Rainfall: mm/hour from OpenWeather
   │   └── Risk Level: "Low", "Moderate", "High"
   └── User can view 3D terrain (placeholder for Cesium)
```

### Data Pipeline (Model Generation)

```
HISTORICAL DATA
├── Global Landslide Catalog
├── Kerala Regional Data (floods, landslides)
└── training CSV file

     ↓ train_models.py

TRAINING PHASE
├── Load CSV into pandas
├── Features: topographic variables (9 features)
├── Target: Binary landslide/safe
├── Train-test split (80-20)
├── Train XGBoost with class weighting
└── Save model.pkl

     ↓ generate_susceptibility_map.py

INFERENCE PHASE
├── Load 9 input rasters (DEM, slope, aspect, etc.)
├── Stack into (H, W, 9) array
├── Flatten to (H×W, 9) matrix
├── Apply XGBoost: predict_proba() → (H×W,)
├── Reshape to (H, W) raster
└── Save susceptibility_ml.tif

     ↓ unet_refine.py

REFINEMENT PHASE
├── Load susceptibility_ml.tif
├── Apply U-Net deep learning model
├── Capture local spatial patterns
└── Save susceptibility_dl.tif (refined)

     ↓ generate_runout_and_fuse.py

RUNOUT & FUSION
├── Compute D8 flow direction from DEM
├── Trace paths from failure zones → streams
├── Create runout_paths.geojson
├── Create transit zone (buffered runout)
├── Create deposition zone (low slope + high flow)
├── Fuse zones with priority: 3=failure, 2=transit, 1=deposition, 0=safe
└── Save hazard_fused.tif + zone masks

     ↓

READY FOR SERVING
├── All .tif files are Cloud-Optimized (COG format)
├── Can be tiled efficiently by rio-tiler
└── Served via FastAPI tile endpoints
```

### Startup Sequence

**When user runs `run-all.bat`:**

```
1. Launches backend window:
   ├── Activates .venv
   ├── Runs: uvicorn app:app --reload --port 8000
   ├── Loads app.py, includes routers (tiles, pixel)
   ├── Mounts /rasters directory
   └── Server ready on http://localhost:8000

2. Waits 2 seconds

3. Launches frontend window:
   ├── Runs: npm run dev
   ├── Starts Vite dev server
   ├── App accessible on http://localhost:5173
   └── HMR (Hot Module Reload) enabled

4. User opens browser to localhost:5173
   ├── Frontend loads React app
   ├── MapView component initializes Leaflet
   ├── Fetches runout_paths.geojson
   └── Ready for interaction
```

---

## Running the Application

### Prerequisites
- Python 3.10+ with pip
- Node.js 18+ with npm
- ~2GB disk space for raster data

### Backend Setup

```bash
# Create virtual environment
cd c:\coding\Slipsense\backend
python -m venv .venv
.\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Frontend Setup

```bash
cd c:\coding\Slipsense\frontend
npm install
```

### Starting the Application

**Option 1: Single Command**
```bash
cd c:\coding\Slipsense
run-all.bat
```
- Launches both backend and frontend in separate windows
- Backend: http://localhost:8000
- Frontend: http://localhost:5173

**Option 2: Separate Terminals**

Terminal 1 (Backend):
```bash
cd c:\coding\Slipsense\backend
.\.venv\Scripts\activate
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Terminal 2 (Frontend):
```bash
cd c:\coding\Slipsense\frontend
npm run dev
```

### Testing

**Backend Health Check:**
```bash
curl http://localhost:8000/
# Expected: {"status": "SlipSense Tile Server running"}
```

**Query Pixel Info:**
```bash
curl "http://localhost:8000/pixel-info?lat=10.5&lon=75.5"
# Expected: JSON with zone, susceptibility, rainfall, riskLevel
```

**Request Map Tile:**
```bash
curl "http://localhost:8000/tiles/hazard_fused/10/512/512.png" --output tile.png
# Expected: PNG image of hazard map
```

---

## Summary Table: Files & Their Roles

| File | Type | Input | Output | Role |
|------|------|-------|--------|------|
| `train_models.py` | Python Script | CSV data | XGBoost .pkl | Train binary classifier |
| `generate_susceptibility_map.py` | Python Script | Rasters + model | susceptibility_ml.tif | Apply ML to region |
| `unet_refine.py` | Python Script | ML raster | susceptibility_dl.tif | Refine with DL |
| `generate_runout_and_fuse.py` | Python Script | DEM, DL raster | hazard_fused.tif + GeoJSON | Create zones + paths |
| `app.py` | FastAPI | HTTP requests | REST API | Entry point for backend |
| `tiles.py` | FastAPI Router | Tile requests | PNG images | Generate map tiles |
| `pixel.py` | FastAPI Router | Coordinates | JSON data | Query pixel values |
| `App.jsx` | React Component | None | UI state | Main app container |
| `MapView.jsx` | React Component | Layers, callbacks | Map display | Leaflet integration |
| `LayerControl.jsx` | React Component | State, callbacks | UI controls | Toggle/opacity |
| `run-all.bat` | Batch Script | None | Running processes | Launch both apps |

---

## Architecture Insights

### Why This Design?

1. **Separation of Concerns**
   - Backend: Data serving & computation
   - Frontend: User interface & visualization
   - ML Scripts: Preprocessing & model generation
   - Allows independent scaling and updates

2. **Performance Optimization**
   - Cloud-Optimized GeoTIFFs (COG) for fast tile serving
   - rio-tiler reads only needed tiles (not entire file)
   - Frontend lazy-loads runout GeoJSON
   - Tile caching by browser

3. **Flexibility**
   - Multiple models (ML & DL) can be displayed simultaneously
   - Layer opacity adjustable for comparison
   - New hazard zones easily added to fusion logic
   - API extensible for future features (3D, time series)

4. **Scalability**
   - Stateless FastAPI backend (can run on any server)
   - Static frontend (can be served by CDN)
   - ML models precomputed (no real-time training)
   - Raster data in optimized format (efficient storage)

---

## Key Concepts

### Landslide Hazard Zones

| Zone | Code | Color | Meaning | Risk Level |
|------|------|-------|---------|-----------|
| **Failure** | 3 | Red | Likely landslide initiation | ⚠️⚠️⚠️ Very High |
| **Transit** | 2 | Orange | Material movement path | ⚠️⚠️ High |
| **Deposition** | 1 | Yellow | Material accumulation | ⚠️ Moderate |
| **Safe** | 0 | Black | Low/no hazard | ✓ Low |

### Key Algorithms

1. **D8 Flow Routing**: Traces 8-connected downslope paths
2. **Binary Classification (XGBoost)**: Predicts landslide probability from features
3. **U-Net Refinement**: Captures spatial patterns for improved predictions
4. **Hazard Fusion**: Combines multiple data sources with priorities
5. **Risk Calculation**: Integrates susceptibility + weather for dynamic risk

---

This comprehensive documentation should give you complete understanding of the SlipSense system architecture, data flow, and implementation details!
