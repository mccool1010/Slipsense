# HOW TO RUN – SlipSense Setup and Usage Guide

## 1. Prerequisites

### 1.1 Software Requirements

| Software | Required Version | Notes |
|----------|------------------|-------|
| Python | 3.9+ | Tested with 3.10, 3.11 |
| Node.js | 18+ | Tested with 18.x, 20.x |
| npm | 8+ | Comes with Node.js |
| Git | Any recent version | For cloning repository |

### 1.2 API Keys (Placeholders)

Create the following environment configuration files with your own API keys:

**Backend** (`backend/.env`):
```env
OPENWEATHER_API_KEY=your_openweather_api_key_here

# SMS Alert Configuration (optional)
SMS_PROVIDER=fast2sms
DRY_RUN=true
FAST2SMS_API_KEY=your_fast2sms_api_key_here
ALERT_RECIPIENTS=+919876543210,+919876543211

# Or for Twilio:
# SMS_PROVIDER=twilio
# TWILIO_ACCOUNT_SID=your_sid
# TWILIO_AUTH_TOKEN=your_token
# TWILIO_FROM_NUMBER=+1234567890
```

**Frontend** (`frontend/.env`):
```env
VITE_API_URL=http://localhost:8000
```

> **Note**: For development and testing, the backend includes a default OpenWeather API key. For production use, obtain your own keys from the respective service providers.

---

## 2. Backend Setup

### 2.1 Navigate to Backend Directory
```bash
cd backend
```

### 2.2 Create Python Virtual Environment
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Linux/macOS
python3 -m venv venv
source venv/bin/activate
```

### 2.3 Install Dependencies
```bash
pip install -r requirements.txt
```

**Required packages** (from `requirements.txt`):
- fastapi
- uvicorn[standard]
- rio-tiler
- rasterio
- Pillow
- python-dotenv
- shapely
- twilio
- requests

### 2.4 Verify Raster Files
Ensure the following files exist in `backend/rasters/`:
- `susceptibility_ml.tif`
- `susceptibility_dl.tif`
- `hazard_fused.tif`
- `transit_mask.tif`
- `deposition_mask.tif`
- `susceptibility_historical_gsi.tif`
- `runout_paths.geojson`

### 2.5 Start FastAPI Server
```bash
python -m uvicorn app:app --reload --port 8000
```

**Expected output**:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### 2.6 Verify Backend is Running
Open browser and navigate to:
- Health check: http://localhost:8000/
- API docs: http://localhost:8000/docs

---

## 3. Frontend Setup

### 3.1 Navigate to Frontend Directory
```bash
cd frontend
```

### 3.2 Install Node Dependencies
```bash
npm install
```

This will install:
- react, react-dom
- leaflet, react-leaflet
- cesium
- framer-motion
- react-icons
- vite (dev server)

### 3.3 Start Development Server
```bash
npm run dev
```

**Expected output**:
```
  VITE v7.0.0  ready in XXX ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: http://192.168.x.x:5173/
  ➜  press h + enter to show help
```

### 3.4 Access the Application
Open browser and navigate to: http://localhost:5173/

---

## 4. Using the System

### 4.1 Map Interface Overview

Upon loading, the application displays:
- **Base Map**: ESRI World Imagery satellite view
- **Default Active Layers**: DL Susceptibility, Final Hazard Map, Runout Paths
- **Side Panel**: Layer controls, legend, and location information
- **Navbar**: Application title and weather information

### 4.2 Layer Toggling

In the **Layers** panel on the left sidebar:

| Layer | Default State | Description |
|-------|---------------|-------------|
| Streets | Off | OpenStreetMap overlay for reference |
| DL Refined Susceptibility | On | U-Net refined probability raster |
| Historical Susceptibility (GSI) | Off | KSDMA/GSI 2022 classification |
| Final Hazard Map | On | Fused zone classification |
| Runout Paths | On | D8-traced flow lines |
| Transit Zone | Off | Movement path overlay |
| Deposition Zone | Off | Accumulation area overlay |

**To toggle a layer**: Click the checkbox next to the layer name.

### 4.3 Opacity Adjustment

When a layer is enabled, an opacity slider appears next to it:
- Drag left (0) for fully transparent
- Drag right (1) for fully opaque
- Useful for comparing overlapping layers

### 4.4 Map Click Inspection

**Click anywhere on the map** to query pixel data:

The **Selected Location** panel displays:
- **Latitude/Longitude**: Clicked coordinates
- **Zone**: Safe, Failure, Transit, or Deposition
- **DL Susceptibility**: Probability value (0–1)
- **GSI Historical**: Low/Moderate/High (if available)
- **Rainfall**: Current mm/hr from weather API
- **Overall Risk**: Computed risk level

### 4.5 Map Hover Inspection

**Hover over the map** to see a tooltip with:
- Zone classification
- Susceptibility value
- Rainfall information

Tooltip appears after brief delay (~200ms) to avoid excessive API calls.

### 4.6 Runout Path Visualization

When **Runout Paths** layer is enabled:
- Cyan lines show predicted debris flow paths
- **Hover** over a path: Line turns red and thickens
- **Click** on a path: Information panel explains D8 algorithm

### 4.7 District Filter (Historical Layer)

When **Historical Susceptibility (GSI)** is enabled:
1. A dropdown appears below the layer toggle
2. Select a specific district (e.g., "Wayanad", "Idukki")
3. Map shows only that district's GSI classification
4. Select "All Districts" to view state-wide data

### 4.8 3D Terrain View

1. Click on a location to select it
2. Click **"View 3D Terrain"** button in the location panel
3. Cesium modal opens with Google Photorealistic 3D Tiles
4. Camera flies to the selected location
5. Click **✖** to close 3D view

### 4.9 Weather Information

After clicking a location:
- Navbar displays current temperature and conditions
- Location panel shows rainfall rate
- Weather data sourced from OpenWeather API

### 4.10 Emergency Alert System (API Only)

The alert system is accessible via API endpoints:

**Check all districts**:
```bash
curl http://localhost:8000/alerts/check
```

**Trigger alerts (dry run)**:
```bash
curl -X POST "http://localhost:8000/alerts/trigger?dry_run=true"
```

**View alert status**:
```bash
curl http://localhost:8000/alerts/status
```

---

## 5. Folder Structure Overview

```
Slipsense/
├── backend/
│   ├── app.py              # FastAPI entry point
│   ├── tiles.py            # XYZ tile generation (rio-tiler)
│   ├── pixel.py            # Pixel inspection API
│   ├── alerts.py           # SMS alert system
│   ├── config.py           # Raster paths and thresholds
│   ├── requirements.txt    # Python dependencies
│   ├── .env                # API keys (create this)
│   └── rasters/            # GeoTIFF rasters and GeoJSON
│       ├── susceptibility_ml.tif
│       ├── susceptibility_dl.tif
│       ├── hazard_fused.tif
│       ├── transit_mask.tif
│       ├── deposition_mask.tif
│       ├── susceptibility_historical_gsi.tif
│       ├── runout_paths.geojson
│       ├── unet_refiner.pth
│       └── districts/       # Per-district GSI rasters
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx         # Main application component
│   │   ├── App.css         # Global styles
│   │   └── components/
│   │       ├── MapView.jsx      # Leaflet map
│   │       ├── CesiumView.jsx   # 3D terrain modal
│   │       ├── LayerControl.jsx # Layer toggles and sliders
│   │       ├── Legend.jsx       # Color legend
│   │       ├── Navbar.jsx       # Top navigation bar
│   │       └── Toast.jsx        # Notification system
│   ├── package.json        # Node dependencies
│   └── vite.config.js      # Vite configuration
│
├── data/                   # Training data (CSV files)
│   ├── kerala_landslide_data.csv
│   ├── kerala_flood_data.csv
│   └── Global_Landslide_Catalog_Export_rows.csv
│
├── ml_models/              # Model training scripts and outputs
│
├── Kerala_District_Boundary.geojson  # District polygons
├── README.md               # Project documentation
├── HOW_TO_RUN.md           # This file
└── run-all.bat             # Windows batch script to start both servers
```

---

## 6. Quick Start (Windows)

Use the provided batch script to start both servers:

```bash
run-all.bat
```

This opens two terminal windows:
1. Backend server (port 8000)
2. Frontend dev server (port 5173)

---

## 7. Troubleshooting

### Backend Issues

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError` | Ensure virtual environment is activated and dependencies installed |
| Raster file not found | Verify files exist in `backend/rasters/` |
| Port 8000 in use | Kill existing process or change port: `--port 8001` |

### Frontend Issues

| Problem | Solution |
|---------|----------|
| `npm install` fails | Clear `node_modules/` and `package-lock.json`, retry |
| Map tiles not loading | Verify backend is running on port 8000 |
| Cesium not loading | Check browser console for CORS or asset path errors |

### API Issues

| Problem | Solution |
|---------|----------|
| Weather returns 500 | Check `OPENWEATHER_API_KEY` in `.env` |
| Pixel info returns 404 | Clicked location may be outside raster coverage |

---

## 8. Testing API Endpoints

### Test Tile Service
```bash
curl http://localhost:8000/tiles/susceptibility_dl/10/752/500.png --output test_tile.png
```

### Test Pixel Inspection
```bash
curl "http://localhost:8000/pixel-info?lat=12.5&lon=75.0"
```

### Test Weather Proxy
```bash
curl "http://localhost:8000/weather?lat=12.5&lon=75.0"
```

### Test Alert System
```bash
curl http://localhost:8000/alerts/test
```

---

*For additional support, refer to README.md or contact the project team.*
