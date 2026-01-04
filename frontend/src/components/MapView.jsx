// src/components/MapView.jsx
import React, { useState, useRef } from "react";
import {
  MapContainer,
  TileLayer,
  GeoJSON,
  useMapEvents,
  ZoomControl,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { motion, AnimatePresence } from "framer-motion";

/* ================================
   Map Click Handler
================================ */
function MapClickHandler({ onMapClick }) {
  useMapEvents({
    click(e) {
      const { lat, lng } = e.latlng;
      // normalize to `lon` key so parent `App.jsx` displays longitude
      onMapClick({ lat, lon: lng });
    },
  });
  return null;
}

/* ================================
   Map Hover Handler
================================ */
function MapHoverHandler({ onHover }) {
  useMapEvents({
    mousemove(e) {
      const { lat, lng } = e.latlng;
      onHover({ lat, lon: lng });
    },
    mouseout() {
      onHover(null);
    },
  });
  return null;
}

/* ================================
   MapView Component
================================ */
const MapView = ({
  activeLayers,
  layerOpacity,
  onMapClick,
  sidebarOpen,
}) => {
  const TILE_SERVER = "http://localhost:8000";
  const [hoverInfo, setHoverInfo] = useState(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const [runoutGeoJSON, setRunoutGeoJSON] = useState(null);
  const hoverTimeoutRef = useRef(null);
  const mapContainerRef = useRef(null);
  const [map, setMap] = React.useState(null);
  const resizeTimeoutRef = useRef(null);

  // Load runout GeoJSON on component mount
  React.useEffect(() => {
    const loadRunoutGeoJSON = async () => {
      try {
        const response = await fetch(`${TILE_SERVER}/rasters/runout_paths.geojson`);
        const data = await response.json();
        console.log("Runout GeoJSON loaded successfully, features:", data.features.length);
        setRunoutGeoJSON(data);
      } catch (error) {
        console.error("Failed to load runout GeoJSON:", error);
      }
    };
    
    loadRunoutGeoJSON();
  }, []);

  const rasterLayers = {
    susceptibilityML: `${TILE_SERVER}/tiles/susceptibility_ml/{z}/{x}/{y}.png`,
    susceptibilityDL: `${TILE_SERVER}/tiles/susceptibility_dl/{z}/{x}/{y}.png`,
    hazardFused: `${TILE_SERVER}/tiles/hazard_fused/{z}/{x}/{y}.png`,
    transit: `${TILE_SERVER}/tiles/transit/{z}/{x}/{y}.png`,
    deposition: `${TILE_SERVER}/tiles/deposition/{z}/{x}/{y}.png`,
  };

  const handleHover = (coords) => {
    if (!coords) {
      setHoverInfo(null);
      return;
    }

    clearTimeout(hoverTimeoutRef.current);
    hoverTimeoutRef.current = setTimeout(async () => {
      try {
        const url = `${TILE_SERVER}/pixel-info?lat=${coords.lat}&lon=${coords.lon}`;
        console.log("Fetching hover data:", url);
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          console.log("Hover data received:", data);
          setHoverInfo({ ...coords, ...data });
        } else {
          console.error("Hover API error: status", res.status);
        }
      } catch (err) {
        console.error("Hover API error:", err);
      }
    }, 200);
  };

  const handleMapMouseMove = (e) => {
    setMousePos({ x: e.clientX, y: e.clientY });
  };

  // Keep Leaflet map size valid when the layout changes (sidebar toggle / window resize)
  React.useEffect(() => {
    if (!map) return;
    const t = setTimeout(() => { try { map.invalidateSize(); } catch (e) {} }, 300);
    return () => clearTimeout(t);
  }, [map, sidebarOpen]);

  React.useEffect(() => {
    if (!map) return;
    const handleResize = () => {
      clearTimeout(resizeTimeoutRef.current);
      resizeTimeoutRef.current = setTimeout(() => {
        try { map.invalidateSize(); } catch (e) {}
      }, 150);
    };
    window.addEventListener("resize", handleResize);
    return () => { window.removeEventListener("resize", handleResize); clearTimeout(resizeTimeoutRef.current); };
  }, [map]);

  return (
    <div 
      ref={mapContainerRef}
      style={{ height: "100%", width: "100%", position: "relative" }}
      onMouseMove={handleMapMouseMove}
    >
      <MapContainer
        center={[12.5, 75.0]}
        zoom={11}
        style={{ height: "100%", width: "100%" }}
        whenCreated={(m) => setMap(m)}
        zoomControl={false}
      >
        {/* Zoom controls in top-right corner */}
        <ZoomControl position="topright" />

        {/* Base map */}
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          attribution="© Esri"
        />

        {/* Optional Streets overlay (OpenStreetMap) */}
        {activeLayers.streets && (
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution="© OpenStreetMap contributors"
            opacity={layerOpacity.streets}
            zIndex={650}
          />
        )}

        {/* Raster overlays */}
        {activeLayers.susceptibilityML && (
          <TileLayer url={rasterLayers.susceptibilityML} opacity={layerOpacity.susceptibilityML} />
        )}
        {activeLayers.susceptibilityDL && (
          <TileLayer url={rasterLayers.susceptibilityDL} opacity={layerOpacity.susceptibilityDL} />
        )}
        {activeLayers.hazardFused && (
          <TileLayer url={rasterLayers.hazardFused} opacity={layerOpacity.hazardFused} />
        )}
        {activeLayers.transit && (
          <TileLayer url={rasterLayers.transit} opacity={layerOpacity.transit} />
        )}
        {activeLayers.deposition && (
          <TileLayer url={rasterLayers.deposition} opacity={layerOpacity.deposition} />
        )}

        {/* Runout paths */}
        {activeLayers.runout && runoutGeoJSON && (
          <>
            {console.log("Rendering runout paths, feature count:", runoutGeoJSON.features.length)}
            <GeoJSON
              data={runoutGeoJSON}
              style={{
                color: "#00ffff",
                weight: 2,
                opacity: layerOpacity.runout,
              }}
              onEachFeature={(feature, layer) => {
                console.log("Runout path feature loaded:", feature);
              layer.on({
                click: () => {
                  onMapClick({
                    type: "runout",
                    message: "Runout path shows the predicted downhill movement of landslide material based on terrain slope and flow direction.",
                  });
                },
                mouseover: () => {
                  layer.setStyle({
                    color: "#ff0000",
                    weight: 4,
                  });
                  layer.bringToFront();
                },
                mouseout: () => {
                  layer.setStyle({
                    color: "#00ffff",
                    weight: 2,
                  });
                },
              });
            }}
            />
          </>
        )}

        {/* Click handler */}
        <MapClickHandler onMapClick={onMapClick} />

        {/* Hover handler */}
        <MapHoverHandler onHover={handleHover} />
      </MapContainer>

      

      {/* Hover tooltip - follows mouse */}
      <AnimatePresence>
        {hoverInfo && (
          <motion.div
            key="hover-tooltip"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.12 }}
            className="map-hover-tooltip rounded-md shadow-lg bg-black text-white p-2 text-xs"
            style={{ position: "fixed", left: `${mousePos.x + 10}px`, top: `${mousePos.y + 10}px` }}
          >
            <div><b>Zone:</b> {hoverInfo.zone}</div>
            <div><b>Susceptibility:</b> {hoverInfo.susceptibility?.toFixed(3)}</div>
            <div><b>Rainfall:</b> {hoverInfo.rainfall} mm/hr</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default MapView;
