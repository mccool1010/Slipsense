# SlipSense – Backend Architecture

> FastAPI-based REST API for tile serving, pixel queries, and alert management

---

## Backend Overview

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '18px'}}}%%
flowchart TB
    subgraph ENTRY["🚀 APPLICATION ENTRY"]
        APP["⚙️ FastAPI<br/>app.py"]
        CORS["🔒 CORS<br/>Middleware"]
        STATIC["📁 Static Files<br/>Mount"]
    end

    subgraph ROUTERS["📡 API ROUTERS"]
        direction LR
        TR["🖼️<br/>tiles_router"]
        PR["📍<br/>pixel_router"]
        AR["🚨<br/>alerts_router"]
    end

    subgraph TILES_SVC["🖼️ TILE SERVICE"]
        COG["📊 COGReader"]
        NORM["📈 Normalize"]
        COLOR["🎨 Colorize"]
        PNG["🖼️ PNG Output"]
    end

    subgraph PIXEL_SVC["📍 PIXEL SERVICE"]
        RIO["📂 rasterio.open()"]
        TRANS["🔄 CRS Transform"]
        QUERY["❓ Read Pixel"]
        RISK["⚠️ Calculate Risk"]
    end

    subgraph ALERT_SVC["🚨 ALERT SERVICE"]
        LOAD["📂 Load Districts"]
        SAMPLE["📍 Sample Points"]
        ASSESS["📊 Risk Assessment"]
        SEND["📱 Send SMS"]
    end

    subgraph EXTERNAL["🌐 EXTERNAL APIS"]
        WEATHER["☁️ OpenWeather"]
        TWILIO["📱 Twilio SMS"]
    end

    subgraph CONFIG["⚙️ CONFIGURATION"]
        CFG["config.py"]
        ENV[".env"]
    end

    APP --> CORS --> STATIC
    APP --> TR & PR & AR
    
    TR --> COG --> NORM --> COLOR --> PNG
    PR --> RIO --> TRANS --> QUERY --> RISK
    AR --> LOAD --> SAMPLE --> ASSESS --> SEND
    
    PR <-.-> WEATHER
    SEND <-.-> TWILIO
    
    CFG --> TR & PR & AR
    ENV --> APP

    style ENTRY fill:#FEE2E2,stroke:#EF4444,stroke-width:3px
    style ROUTERS fill:#DBEAFE,stroke:#3B82F6,stroke-width:3px
    style TILES_SVC fill:#FEF3C7,stroke:#F59E0B,stroke-width:3px
    style PIXEL_SVC fill:#D1FAE5,stroke:#10B981,stroke-width:3px
    style ALERT_SVC fill:#F3E8FF,stroke:#8B5CF6,stroke-width:3px
    style EXTERNAL fill:#E0E7FF,stroke:#4F46E5,stroke-width:3px
    style CONFIG fill:#FDF4FF,stroke:#A855F7,stroke-width:2px
```

> 📥 **Download**: Open in [Mermaid Live Editor](https://mermaid.live) → Click "Actions" → "Download PNG/SVG"

---

## API Endpoints

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '16px'}}}%%
flowchart LR
    subgraph ENDPOINTS["📡 API ENDPOINTS"]
        direction TB
        
        subgraph TILES["🖼️ Tile Endpoints"]
            T1["/tiles/{layer}/{z}/{x}/{y}.png"]
        end
        
        subgraph PIXEL["📍 Pixel Endpoints"]
            P1["/pixel-info"]
            P2["/weather"]
        end
        
        subgraph ALERTS["🚨 Alert Endpoints"]
            A1["/alerts/status"]
            A2["/alerts/trigger"]
            A3["/alerts/settings"]
        end
        
        subgraph STATIC["📁 Static Files"]
            S1["/rasters/*"]
        end
    end

    style TILES fill:#FEF3C7,stroke:#F59E0B,stroke-width:2px
    style PIXEL fill:#D1FAE5,stroke:#10B981,stroke-width:2px
    style ALERTS fill:#F3E8FF,stroke:#8B5CF6,stroke-width:2px
    style STATIC fill:#E0E7FF,stroke:#4F46E5,stroke-width:2px
```

> 📥 **Download**: Open in [Mermaid Live Editor](https://mermaid.live) → Click "Actions" → "Download PNG/SVG"

---

## Request Flow: Tile Request

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '16px'}}}%%
sequenceDiagram
    participant Browser
    participant FastAPI
    participant rio-tiler
    participant Raster

    Browser->>FastAPI: GET /tiles/susceptibility_dl/10/752/500.png
    FastAPI->>rio-tiler: COGReader.tile(752, 500, 10)
    rio-tiler->>Raster: Read tile from susceptibility_dl.tif
    Raster-->>rio-tiler: numpy array (256×256)
    rio-tiler-->>FastAPI: tile data
    FastAPI->>FastAPI: Normalize & Apply Colormap
    FastAPI-->>Browser: PNG image bytes
```

> 📥 **Download**: Open in [Mermaid Live Editor](https://mermaid.live) → Click "Actions" → "Download PNG/SVG"

---

## Request Flow: Pixel Query

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '16px'}}}%%
sequenceDiagram
    participant Browser
    participant FastAPI
    participant rasterio
    participant OpenWeather

    Browser->>FastAPI: GET /pixel-info?lat=12.5&lon=75.0
    FastAPI->>rasterio: Open susceptibility_dl.tif
    rasterio-->>FastAPI: Pixel value at coords
    FastAPI->>rasterio: Open hazard_fused.tif
    rasterio-->>FastAPI: Zone code
    FastAPI->>OpenWeather: GET weather?lat=12.5&lon=75.0
    OpenWeather-->>FastAPI: {rain: {1h: 2.5}, ...}
    FastAPI->>FastAPI: risk = sus × (1 + rain/20)
    FastAPI-->>Browser: {zone, susceptibility, rainfall, riskLevel}
```

> 📥 **Download**: Open in [Mermaid Live Editor](https://mermaid.live) → Click "Actions" → "Download PNG/SVG"

---

## Backend Files

| File | Purpose | Key Functions |
|------|---------|---------------|
| `app.py` | Application entry | FastAPI setup, router mounting |
| `config.py` | Configuration | Raster paths, thresholds |
| `tiles.py` | Tile service | COG reading, colorization |
| `pixel.py` | Pixel queries | Coordinate lookup, risk calculation |
| `alerts.py` | Alert system | SMS triggers, district sampling |

---

## Raster Files Served

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '16px'}}}%%
flowchart TB
    subgraph RASTERS["📂 RASTER FILES"]
        direction LR
        
        subgraph SUS["Susceptibility"]
            ML["susceptibility_ml.tif"]
            DL["susceptibility_dl.tif"]
            HIST["susceptibility_historical_gsi.tif"]
        end
        
        subgraph HAZ["Hazard Zones"]
            FUSED["hazard_fused.tif"]
            TRANS["transit_mask.tif"]
            DEPO["deposition_mask.tif"]
        end
        
        subgraph PATHS["Vector Data"]
            RUN["runout_paths.geojson"]
        end
    end

    style SUS fill:#D1FAE5,stroke:#10B981,stroke-width:2px
    style HAZ fill:#FEE2E2,stroke:#EF4444,stroke-width:2px
    style PATHS fill:#DBEAFE,stroke:#3B82F6,stroke-width:2px
```

> 📥 **Download**: Open in [Mermaid Live Editor](https://mermaid.live) → Click "Actions" → "Download PNG/SVG"

---

*Part of the SlipSense Architecture Documentation*
