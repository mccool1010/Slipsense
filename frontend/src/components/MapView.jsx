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
// Configurable so a deployed build can point at a real host; falls back to localhost
// for development. Module scope, so effects do not need it as a dependency.
const TILE_SERVER = import.meta.env.VITE_TILE_SERVER || "http://localhost:8000";

// Velocity ramp for runout corridors: blue slow, red fast. Matches the colouring used
// in ml_models/runout_figure.py so the app and the figures tell the same story.
function velocityColor(v) {
  if (v == null || Number.isNaN(v)) return "#00ffff";
  const t = Math.max(0, Math.min(1, v / 25));
  const hue = (1 - t) * 210; // 210 = blue, 0 = red
  return `hsl(${hue}, 90%, 52%)`;
}

// Corridors that fall further carry more energy, so draw them heavier.
function corridorWeight(dropM) {
  if (dropM == null || Number.isNaN(dropM)) return 2;
  return Math.max(1.5, Math.min(6, 1.5 + dropM / 120));
}

const MapView = ({
  activeLayers,
  layerOpacity,
  onMapClick,
  sidebarOpen,
  selectedDistrict = "all",
}) => {
  const [hoverInfo, setHoverInfo] = useState(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const [runoutGeoJSON, setRunoutGeoJSON] = useState(null);
  // Animation of the runout corridors: a marching dash pattern that reads as debris
  // travelling downslope. Off unless the runout layer is on, so it costs nothing when
  // the layer is hidden.
  const [dashOffset, setDashOffset] = useState(0);
  const runoutAnimating = Boolean(activeLayers.runout);
  const hoverTimeoutRef = useRef(null);
  const mapContainerRef = useRef(null);
  const [map, setMap] = React.useState(null);
  const resizeTimeoutRef = useRef(null);

  // Advance the dash pattern while the runout layer is visible.
  React.useEffect(() => {
    if (!runoutAnimating) return undefined;
    const id = setInterval(() => setDashOffset((d) => (d + 2) % 20), 90);
    return () => clearInterval(id);
  }, [runoutAnimating]);

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

  // Construct historical susceptibility URL with district filter
  const historicalUrl = selectedDistrict === "all"
    ? `${TILE_SERVER}/tiles/historical_susceptibility/{z}/{x}/{y}.png`
    : `${TILE_SERVER}/tiles/historical_susceptibility/{z}/{x}/{y}.png?district=${selectedDistrict}`;

  const rasterLayers = {
    susceptibilityML: `${TILE_SERVER}/tiles/susceptibility_ml/{z}/{x}/{y}.png`,
    susceptibilityDL: `${TILE_SERVER}/tiles/susceptibility_dl/{z}/{x}/{y}.png`,
    uncertainty: `${TILE_SERVER}/tiles/uncertainty/{z}/{x}/{y}.png`,
    historicalSusceptibility: historicalUrl,
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
    const t = setTimeout(() => { try { map.invalidateSize(); } catch (e) { } }, 300);
    return () => clearTimeout(t);
  }, [map, sidebarOpen]);

  React.useEffect(() => {
    if (!map) return;
    const handleResize = () => {
      clearTimeout(resizeTimeoutRef.current);
      resizeTimeoutRef.current = setTimeout(() => {
        try { map.invalidateSize(); } catch (e) { }
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
        {activeLayers.uncertainty && (
          <TileLayer url={rasterLayers.uncertainty} opacity={layerOpacity.uncertainty} />
        )}
        {activeLayers.susceptibilityDL && (
          <TileLayer url={rasterLayers.susceptibilityDL} opacity={layerOpacity.susceptibilityDL} />
        )}
        {activeLayers.historicalSusceptibility && (
          <TileLayer
            key={`historical-${selectedDistrict}`}
            url={rasterLayers.historicalSusceptibility}
            opacity={layerOpacity.historicalSusceptibility}
          />
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
              key={`runout-${runoutAnimating ? "anim" : "static"}`}
              data={runoutGeoJSON}
              style={(feature) => ({
                // Colour by modelled velocity and scale width by the drop the corridor
                // spans, so a short creep and a fast, high-energy surge are visually
                // distinct rather than both drawn as the same cyan thread.
                color: velocityColor(feature?.properties?.max_velocity_ms),
                weight: corridorWeight(feature?.properties?.drop_m),
                opacity: layerOpacity.runout,
                // A dash offset animated over time reads as material travelling down
                // the corridor, which is what the velocity field actually describes.
                dashArray: runoutAnimating ? "8 12" : null,
                dashOffset: runoutAnimating ? String(-dashOffset) : null,
                lineCap: "round",
              })}
              onEachFeature={(feature, layer) => {
                const p = feature?.properties || {};
                layer.bindTooltip(
                  `<b>Runout corridor</b><br/>` +
                  `Length ${p.length_m ?? "?"} m<br/>` +
                  `Drop ${p.drop_m ?? "?"} m<br/>` +
                  `Max velocity ${p.max_velocity_ms ?? "?"} m/s<br/>` +
                  `Reach angle ${p.reach_angle_deg ?? "?"}°` +
                  (p.buildings_at_risk != null
                    ? `<br/>Buildings at risk ${p.buildings_at_risk}` +
                      `<br/>Road at risk ${p.road_km_at_risk ?? 0} km`
                    : ""),
                  { sticky: true }
                );
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
