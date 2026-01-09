# SlipSense – System Architecture Walkthrough

This document provides detailed visual diagrams showing how every component of SlipSense interacts, from ML model training to frontend visualization.

> **Note**: The diagrams below use Mermaid syntax. They render automatically on GitHub, or in VS Code with the "Markdown Preview Mermaid Support" extension.

---

## Complete System Flow

```mermaid
flowchart TB
    subgraph DataSources["📂 Data Sources"]
        DEM["DEM (30m)"]
        Historical["Historical Landslides"]
        GSI["GSI/KSDMA Data"]
        Districts["District Boundaries"]
    end

    subgraph MLPipeline["🤖 ML/DL Pipeline"]
        Features["Feature Extraction"]
        RF["Random Forest Model"]
        UNET["U-Net Refinement"]
        D8["D8 Flow Direction"]
        Fusion["Hazard Fusion"]
    end

    subgraph Rasters["📊 Output Rasters"]
        ML_OUT["susceptibility_ml.tif"]
        DL_OUT["susceptibility_dl.tif"]
        HAZARD["hazard_fused.tif"]
        RUNOUT["runout_paths.geojson"]
    end

    subgraph Backend["⚙️ FastAPI Backend"]
        TILES["Tile Service"]
        PIXEL["Pixel API"]
        WEATHER["Weather Proxy"]
        ALERTS["Alert System"]
    end

    subgraph Frontend["🖥️ React Frontend"]
        LEAFLET["Leaflet Map"]
        CESIUM["Cesium 3D"]
        CONTROLS["Layer Controls"]
        INFO["Info Panels"]
    end

    DEM --> Features
    Historical --> RF
    Features --> RF
    RF --> ML_OUT
    ML_OUT --> UNET
    UNET --> DL_OUT
    DL_OUT --> D8
    D8 --> RUNOUT
    DL_OUT --> Fusion
    RUNOUT --> Fusion
    Fusion --> HAZARD
    GSI --> Rasters
    
    Rasters --> TILES
    Rasters --> PIXEL
    Districts --> ALERTS
    
    TILES --> LEAFLET
    PIXEL --> INFO
    WEATHER --> INFO
    ALERTS --> Backend
    
    LEAFLET --> CONTROLS
    LEAFLET --> CESIUM
    CONTROLS --> LEAFLET
```

---

## ML/DL Model Pipeline

```mermaid
flowchart LR
    subgraph Input["Input Data"]
        DEM["DEM_filled_75.tif"]
    end

    subgraph FeatureExtraction["Feature Extraction"]
        SLOPE["slope75.tif"]
        ASPECT["aspect75.tif"]
        FLOW["Flow_Accumulation75.tif"]
        TWI["TWI_FINAL.tif"]
        SPI["SPI75.tif"]
        RELIEF["Relative_Relief_75.tif"]
        DRAIN["Drainage_Density_Final.tif"]
        RIVER["Distance_to_River_75.tif"]
    end

    subgraph Training["Model Training"]
        LABELS["Landslide Labels"]
        RF["Random Forest"]
    end

    subgraph Refinement["Spatial Refinement"]
        UNET["U-Net CNN"]
        WEIGHTS["unet_refiner.pth"]
    end

    subgraph Runout["Runout Modeling"]
        D8["D8 Algorithm"]
        TRACE["Path Tracing"]
    end

    subgraph Outputs["Final Outputs"]
        ML["susceptibility_ml.tif"]
        DL["susceptibility_dl.tif"]
        PATHS["runout_paths.geojson"]
        TRANSIT["transit_mask.tif"]
        DEPO["deposition_mask.tif"]
        FUSED["hazard_fused.tif"]
    end

    DEM --> SLOPE & ASPECT & FLOW & TWI & SPI & RELIEF & DRAIN & RIVER
    
    SLOPE & ASPECT & FLOW & TWI & SPI & RELIEF & DRAIN & RIVER --> RF
    LABELS --> RF
    RF --> ML
    
    ML --> UNET
    SLOPE --> UNET
    WEIGHTS --> UNET
    UNET --> DL
    
    DL --> D8
    DEM --> D8
    D8 --> TRACE
    TRACE --> PATHS & TRANSIT & DEPO
    
    DL & TRANSIT & DEPO --> FUSED
```

### Feature Extraction Explanation

| Feature | Source | Calculation | Purpose |
|---------|--------|-------------|---------|
| Slope | DEM | Gradient magnitude | Steepness indicator |
| Aspect | DEM | Gradient direction | Sun exposure, moisture |
| Flow Accumulation | DEM | Upstream cell count | Drainage concentration |
| TWI | DEM + Slope | ln(FlowAcc / tan(slope)) | Soil moisture potential |
| SPI | DEM + Slope | FlowAcc × tan(slope) | Erosive power |
| Relative Relief | DEM | Local elevation range | Terrain ruggedness |
| Drainage Density | Flow network | Stream length / area | Channel intensity |
| Distance to River | Flow network | Euclidean distance | Proximity to drainage |

---

## Backend Architecture

```mermaid
flowchart TB
    subgraph FastAPI["FastAPI Application (app.py)"]
        MAIN["app = FastAPI()"]
        CORS["CORS Middleware"]
        STATIC["StaticFiles Mount"]
    end

    subgraph Routers["API Routers"]
        TR["tiles_router"]
        PR["pixel_router"]
        AR["alerts_router"]
    end

    subgraph TileService["Tile Service (tiles.py)"]
        COG["COGReader"]
        NORM["Normalize Band"]
        COLOR["Colorize Hazard"]
        PNG["PNG Response"]
    end

    subgraph PixelService["Pixel Service (pixel.py)"]
        RIO["rasterio.open()"]
        TRANSFORM["CRS Transform"]
        QUERY["Read Pixel Value"]
        RISK["Calculate Risk"]
    end

    subgraph AlertService["Alert Service (alerts.py)"]
        LOAD["Load Districts"]
        SAMPLE["Sample Points"]
        ASSESS["Risk Assessment"]
        SMS["Send SMS"]
    end

    subgraph External["External Services"]
        OW["OpenWeather API"]
        TWILIO["Twilio/Fast2SMS"]
    end

    MAIN --> CORS --> STATIC
    MAIN --> TR & PR & AR
    
    TR --> COG --> NORM --> COLOR --> PNG
    PR --> RIO --> TRANSFORM --> QUERY --> RISK
    PR --> OW
    AR --> LOAD --> SAMPLE --> ASSESS
    ASSESS --> SMS --> TWILIO
```

---

## API Endpoint Flow

```mermaid
sequenceDiagram
    participant Browser
    participant FastAPI
    participant rio-tiler
    participant rasterio
    participant OpenWeather
    participant Twilio

    Note over Browser,Twilio: Tile Request Flow
    Browser->>FastAPI: GET /tiles/susceptibility_dl/10/752/500.png
    FastAPI->>rio-tiler: COGReader.tile(752, 500, 10)
    rio-tiler->>FastAPI: numpy array (256x256)
    FastAPI->>FastAPI: Normalize & Colorize
    FastAPI->>Browser: PNG image bytes

    Note over Browser,Twilio: Pixel Query Flow
    Browser->>FastAPI: GET /pixel-info?lat=12.5&lon=75.0
    FastAPI->>rasterio: Open susceptibility_dl.tif
    rasterio->>FastAPI: Pixel value at coords
    FastAPI->>rasterio: Open hazard_fused.tif
    rasterio->>FastAPI: Zone code
    FastAPI->>OpenWeather: GET weather?lat=12.5&lon=75.0
    OpenWeather->>FastAPI: {rain: {1h: 2.5}, ...}
    FastAPI->>FastAPI: risk = sus × (1 + rain/20)
    FastAPI->>Browser: {zone, susceptibility, rainfall, riskLevel}

    Note over Browser,Twilio: Alert Trigger Flow
    Browser->>FastAPI: POST /alerts/trigger?dry_run=false
    FastAPI->>FastAPI: Load district boundaries
    loop For each district
        FastAPI->>rasterio: Sample susceptibility
        FastAPI->>rasterio: Check hazard zones
        FastAPI->>OpenWeather: Get rainfall
        FastAPI->>FastAPI: Evaluate thresholds
    end
    FastAPI->>Twilio: Send SMS (if triggered)
    FastAPI->>Browser: {alerts_triggered: N, alerts: [...]}
```

---

## Frontend Architecture

```mermaid
flowchart TB
    subgraph App["App.jsx"]
        STATE["Application State"]
        HANDLERS["Event Handlers"]
    end

    subgraph Components["React Components"]
        NAVBAR["Navbar.jsx"]
        MAP["MapView.jsx"]
        LAYER["LayerControl.jsx"]
        LEGEND["Legend.jsx"]
        CESIUM["CesiumView.jsx"]
        TOAST["Toast.jsx"]
    end

    subgraph MapView["MapView.jsx Internals"]
        CONTAINER["MapContainer"]
        BASE["ESRI Basemap"]
        RASTERS["TileLayer (rasters)"]
        GEOJSON["GeoJSON (runout)"]
        CLICK["MapClickHandler"]
        HOVER["MapHoverHandler"]
    end

    subgraph Backend["Backend API"]
        TILES_API["/tiles/{layer}/{z}/{x}/{y}.png"]
        PIXEL_API["/pixel-info"]
        WEATHER_API["/weather"]
        STATIC_API["/rasters/runout_paths.geojson"]
    end

    STATE --> MAP & LAYER & LEGEND & NAVBAR
    HANDLERS --> STATE
    
    MAP --> CONTAINER
    CONTAINER --> BASE & RASTERS & GEOJSON & CLICK & HOVER
    
    RASTERS --> TILES_API
    GEOJSON --> STATIC_API
    CLICK --> PIXEL_API
    CLICK --> WEATHER_API
    HOVER --> PIXEL_API
    
    LAYER --> STATE
    NAVBAR --> STATE
    
    STATE --> CESIUM
    TOAST --> App
```

---

## Component Interaction Flow

```mermaid
sequenceDiagram
    participant User
    participant App
    participant MapView
    participant LayerControl
    participant Backend

    Note over User,Backend: Layer Toggle Flow
    User->>LayerControl: Click "DL Susceptibility" checkbox
    LayerControl->>App: onToggle("susceptibilityDL")
    App->>App: setActiveLayers({...prev, susceptibilityDL: true})
    App->>MapView: Pass updated activeLayers prop
    MapView->>MapView: Render TileLayer conditionally
    MapView->>Backend: Request tiles for visible area
    Backend->>MapView: PNG tiles
    MapView->>User: Display layer on map

    Note over User,Backend: Map Click Flow
    User->>MapView: Click on map location
    MapView->>App: onMapClick({lat: 12.5, lon: 75.0})
    App->>Backend: GET /pixel-info?lat=12.5&lon=75.0
    Backend->>App: {zone, susceptibility, riskLevel}
    App->>Backend: GET /weather?lat=12.5&lon=75.0
    Backend->>App: {temp, humidity, rain}
    App->>App: setSelectedPoint(data)
    App->>App: setWeatherData(weather)
    App->>User: Display info in sidebar

    Note over User,Backend: 3D View Flow
    User->>App: Click "View 3D Terrain"
    App->>App: setShow3D(true)
    App->>CesiumView: Render with lat/lon props
    CesiumView->>CesiumView: Initialize Cesium Viewer
    CesiumView->>CesiumION: Load 3D Tiles (asset 2275207)
    CesiumView->>CesiumView: camera.flyTo(lat, lon)
    CesiumView->>User: Display 3D terrain
```

---

## State Management

```mermaid
flowchart TB
    subgraph AppState["App.jsx State"]
        LAYERS["activeLayers"]
        OPACITY["layerOpacity"]
        POINT["selectedPoint"]
        WEATHER["weatherData"]
        SHOW3D["show3D"]
        SIDEBAR["sidebarOpen"]
        DISTRICT["selectedDistrict"]
    end

    subgraph Handlers["State Update Handlers"]
        TOGGLE["toggleLayer()"]
        OPCHANGE["changeOpacity()"]
        MAPCLICK["handleMapClick()"]
        OPEN3D["open3DView()"]
        CLOSE3D["close3DView()"]
        TOGSB["toggleSidebar()"]
    end

    subgraph Consumers["State Consumers"]
        MV["MapView"]
        LC["LayerControl"]
        CV["CesiumView"]
        NB["Navbar"]
        INFO["Info Panel"]
    end

    TOGGLE --> LAYERS
    OPCHANGE --> OPACITY
    MAPCLICK --> POINT & WEATHER
    OPEN3D --> SHOW3D
    CLOSE3D --> SHOW3D
    TOGSB --> SIDEBAR

    LAYERS --> MV & LC
    OPACITY --> MV & LC
    POINT --> INFO & CV
    WEATHER --> NB & INFO
    SHOW3D --> CV
    SIDEBAR --> MV
    DISTRICT --> MV & LC
```

---

## Alert System Logic

```mermaid
flowchart TB
    START["Trigger Alert Check"]
    
    subgraph ForEachDistrict["For Each District"]
        LOAD["Load District Polygon"]
        SAMPLE["Sample 50 Random Points"]
        
        subgraph Checks["Threshold Checks"]
            SUS["Read DL Susceptibility"]
            HAZ["Check Hazard Zones"]
            RAIN["Fetch Rainfall Data"]
        end
        
        EVAL["Evaluate Conditions"]
        LEVEL["Determine Risk Level"]
    end

    subgraph Conditions["Alert Trigger Conditions"]
        C1["avg OR max susceptibility ≥ 0.75"]
        C2["rainfall ≥ 50mm/24hr"]
        C3["Contains Failure OR Transit zone"]
    end

    subgraph Actions["Alert Actions"]
        LOG["Log Alert"]
        SMS["Send SMS"]
        TRACK["Track Sent Alert"]
    end

    START --> LOAD --> SAMPLE
    SAMPLE --> SUS & HAZ & RAIN
    SUS & HAZ & RAIN --> EVAL
    EVAL --> C1 & C2 & C3
    C1 & C2 & C3 -->|ALL TRUE| LEVEL
    LEVEL -->|VERY HIGH| LOG --> SMS --> TRACK
    LEVEL -->|Other| LOG
```

---

## File Dependencies

```mermaid
flowchart LR
    subgraph Config["config.py"]
        RASTERS["RASTERS dict"]
        DISTRICT_RASTERS["DISTRICT_RASTERS dict"]
        THRESHOLDS["Risk Thresholds"]
    end

    subgraph Backend["Backend Modules"]
        APP["app.py"]
        TILES["tiles.py"]
        PIXEL["pixel.py"]
        ALERTS["alerts.py"]
    end

    subgraph Files["Raster Files"]
        ML_TIF["susceptibility_ml.tif"]
        DL_TIF["susceptibility_dl.tif"]
        HAZ_TIF["hazard_fused.tif"]
        HIST_TIF["susceptibility_historical_gsi.tif"]
        TRANS_TIF["transit_mask.tif"]
        DEPO_TIF["deposition_mask.tif"]
        RUNOUT_GJ["runout_paths.geojson"]
    end

    APP --> TILES & PIXEL & ALERTS
    TILES --> RASTERS
    PIXEL --> RASTERS
    ALERTS --> RASTERS & DISTRICT_RASTERS & THRESHOLDS
    
    RASTERS --> ML_TIF & DL_TIF & HAZ_TIF & HIST_TIF & TRANS_TIF & DEPO_TIF
    RASTERS --> RUNOUT_GJ
```

---

## Data Flow Summary

| Source | Processing | Output | Consumer |
|--------|------------|--------|----------|
| DEM raster | Feature extraction | 9 derived rasters | ML model |
| Features + Labels | Random Forest training | susceptibility_ml.tif | U-Net input |
| ML output + Terrain | U-Net refinement | susceptibility_dl.tif | D8 model, Frontend |
| DL output + DEM | D8 flow tracing | runout_paths.geojson | Frontend |
| All outputs | Zone fusion | hazard_fused.tif | Frontend, Alerts |
| User click | Backend query | Pixel data | Info panel |
| Coordinates | OpenWeather API | Weather data | Navbar, Info panel |
| District polygons | Risk assessment | Alert decision | SMS service |

---

## How to View These Diagrams

### Option 1: GitHub (Recommended)
Push this file to GitHub - diagrams render automatically.

### Option 2: VS Code Extension
1. Install extension: **"Markdown Preview Mermaid Support"**
2. Open this file
3. Press `Ctrl+Shift+V` to preview

### Option 3: Online Viewer
Copy content to [mermaid.live](https://mermaid.live) to view individual diagrams.

---

*SlipSense – A terrain-aware approach to landslide hazard assessment for Kerala*
