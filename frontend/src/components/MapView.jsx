// src/components/MapView.jsx
import React, { useState, useRef } from "react";
import {
  MapContainer,
  TileLayer,
  GeoJSON,
  Rectangle,
  useMapEvents,
  ZoomControl,
  ScaleControl,
  useMap,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { API_BASE, BACKEND_UNREACHABLE } from "../api";
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
   Basemaps
================================ */
// A susceptibility ramp reads very differently over satellite imagery than over a plain
// canvas; offering the choice costs nothing and makes the overlays legible in both.
const BASEMAPS = {
  satellite: {
    label: "Satellite",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "© Esri",
  },
  terrain: {
    label: "Terrain",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Shaded_Relief/MapServer/tile/{z}/{y}/{x}",
    attribution: "© Esri",
  },
  streets: {
    label: "Streets",
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: "© OpenStreetMap contributors",
  },
};

/* ================================
   Zoom tracker
================================ */
// Corridors are 395 polylines with an animated dash pattern. Drawn at regional zoom
// they collapse into illegible specks and still cost a full redraw every 90 ms, so the
// layer is hidden until the view is close enough for it to mean anything.
function ZoomWatcher({ onZoom }) {
  const map = useMap();
  useMapEvents({
    zoomend: () => onZoom(map.getZoom()),
  });
  React.useEffect(() => { onZoom(map.getZoom()); }, [map, onZoom]);
  return null;
}

/* ================================
   MapView Component
================================ */
// Configurable so a deployed build can point at a real host; falls back to localhost
// for development. Module scope, so effects do not need it as a dependency.
const TILE_SERVER = API_BASE;

// A deployed build that fell back to localhost cannot reach any backend, and the
// symptom - base map fine, every overlay empty - is indistinguishable from the layers
// being broken. That ambiguity has cost enough time on this project already, so say it
// plainly instead of letting it look like a model problem.
const MISCONFIGURED_BACKEND = BACKEND_UNREACHABLE;

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
  // Footprint of the modelled layers. Everything outside it is legitimately
  // transparent, which is indistinguishable from a broken layer unless the extent is
  // shown and the view starts inside it.
  const [coverage, setCoverage] = useState(null);
  const [basemap, setBasemap] = useState("satellite");
  const [zoom, setZoom] = useState(11);
  const [cursor, setCursor] = useState(null);
  // Below this the corridors are sub-pixel; see ZoomWatcher.
  const RUNOUT_MIN_ZOOM = 11;
  const runoutVisible = Boolean(activeLayers.runout) && zoom >= RUNOUT_MIN_ZOOM;
  const runoutAnimating = runoutVisible;
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

  // Discover where the modelled layers actually have data, then frame the map on it.
  React.useEffect(() => {
    const loadBounds = async () => {
      try {
        const res = await fetch(`${TILE_SERVER}/layers/bounds`);
        if (!res.ok) return;
        const all = await res.json();
        const b = all.susceptibility_ml?.bounds;
        if (b) setCoverage(b);
      } catch (err) {
        console.warn("Could not load layer bounds:", err);
      }
    };
    loadBounds();
  }, []);

  React.useEffect(() => {
    if (!map || !coverage) return;
    map.fitBounds(coverage, { padding: [24, 24] });
  }, [map, coverage]);

  // Load runout GeoJSON on component mount
  React.useEffect(() => {
    const loadRunoutGeoJSON = async () => {
      try {
        // The v2 corridors. `/rasters/runout_paths.geojson` still resolves to the
        // pre-rebuild file, which was produced by routing debris across a slope
        // raster mistaken for a DEM.
        const response = await fetch(
          `${TILE_SERVER}/rasters/v2/runout_paths_exposed.geojson`
        );
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
    setCursor(coords);
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
      {/* Basemap switcher, coordinate readout and a caption naming the modelled area.
          Without the caption, transparent-because-out-of-coverage is impossible to
          tell apart from transparent-because-broken. */}
      {MISCONFIGURED_BACKEND && (
        <div className="map-config-warning">
          <b>No backend configured.</b> This build points at{" "}
          <code>{TILE_SERVER}</code>, which does not exist for visitors, so no
          susceptibility, runout or hover data can load. Set{" "}
          <code>VITE_TILE_SERVER</code> to the API URL and redeploy.
        </div>
      )}

      <div className="map-hud">
        <div className="map-hud-row">
          {Object.entries(BASEMAPS).map(([key, cfg]) => (
            <button
              key={key}
              type="button"
              className={`map-hud-btn${basemap === key ? " is-active" : ""}`}
              onClick={() => setBasemap(key)}
            >
              {cfg.label}
            </button>
          ))}
        </div>
        <div className="map-hud-meta">
          {cursor
            ? `${cursor.lat.toFixed(4)}, ${cursor.lon.toFixed(4)}`
            : "move over the map"}
          {"  ·  z"}{zoom}
        </div>
        {coverage && (
          <div className="map-hud-meta">
            Modelled area: Kasaragod &amp; Kannur + Karnataka Ghats
            {activeLayers.runout && zoom < RUNOUT_MIN_ZOOM
              ? `  ·  zoom in to z${RUNOUT_MIN_ZOOM} for corridors`
              : ""}
          </div>
        )}
      </div>

      <MapContainer
        center={[12.5, 75.0]}
        zoom={11}
        style={{ height: "100%", width: "100%" }}
        // react-leaflet removed `whenCreated` in v4; this project is on v5, so that
        // callback never fired and `map` stayed null - which silently disabled the
        // invalidateSize handlers below as well as the fit-to-coverage effect.
        ref={setMap}
        zoomControl={false}
      >
        {/* Zoom controls in top-right corner */}
        <ZoomControl position="topright" />

        {/* Base map */}
        <TileLayer
          key={basemap}
          url={BASEMAPS[basemap].url}
          attribution={BASEMAPS[basemap].attribution}
        />

        <ScaleControl position="bottomleft" imperial={false} />
        <ZoomWatcher onZoom={setZoom} />

        {/* Optional Streets overlay (OpenStreetMap) */}
        {activeLayers.streets && (
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution="© OpenStreetMap contributors"
            opacity={layerOpacity.streets}
            zIndex={650}
          />
        )}

        {/* Where the modelled layers have data. Without this the app looks broken
            when panned away, because the footprint is ~1 square degree of a
            Kerala-wide view. */}
        {coverage && (
          <Rectangle
            bounds={coverage}
            pathOptions={{
              color: "#38bdf8",
              weight: 1.5,
              fill: false,
              dashArray: "6 6",
              interactive: false,
            }}
          />
        )}

        {/* Raster overlays */}
        {activeLayers.susceptibilityML && (
          <TileLayer url={rasterLayers.susceptibilityML} opacity={layerOpacity.susceptibilityML} bounds={coverage ?? undefined} />
        )}
        {activeLayers.uncertainty && (
          <TileLayer url={rasterLayers.uncertainty} opacity={layerOpacity.uncertainty} bounds={coverage ?? undefined} />
        )}
        {activeLayers.susceptibilityDL && (
          <TileLayer url={rasterLayers.susceptibilityDL} opacity={layerOpacity.susceptibilityDL} bounds={coverage ?? undefined} />
        )}
        {activeLayers.historicalSusceptibility && (
          <TileLayer
            key={`historical-${selectedDistrict}`}
            url={rasterLayers.historicalSusceptibility}
            opacity={layerOpacity.historicalSusceptibility}
          />
        )}
        {activeLayers.hazardFused && (
          <TileLayer url={rasterLayers.hazardFused} opacity={layerOpacity.hazardFused} bounds={coverage ?? undefined} />
        )}
        {activeLayers.transit && (
          <TileLayer url={rasterLayers.transit} opacity={layerOpacity.transit} bounds={coverage ?? undefined} />
        )}
        {activeLayers.deposition && (
          <TileLayer url={rasterLayers.deposition} opacity={layerOpacity.deposition} bounds={coverage ?? undefined} />
        )}

        {/* Runout paths */}
        {runoutVisible && runoutGeoJSON && (
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
                  // Most centrelines threaten nothing; saying "0 buildings" on every
                  // one of them is noise, so exposure only appears where it exists.
                  (p.buildings_at_risk > 0
                    ? `<br/>Buildings at risk ${p.buildings_at_risk}` : "") +
                  (p.road_km_at_risk > 0
                    ? `<br/>Road at risk ${p.road_km_at_risk} km` : ""),
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
