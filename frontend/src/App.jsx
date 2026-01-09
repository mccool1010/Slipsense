/* App.jsx — SlipSense (Refactored Step 1) */

import React, { useState, useCallback } from "react";
import "./App.css";
import { motion, AnimatePresence } from "framer-motion";
import MapView from "./components/MapView";
import LayerControl from "./components/LayerControl";
import Legend from "./components/Legend";
import CesiumView from "./components/CesiumView";
import Navbar from "./components/Navbar";
import { ToastProvider, useToast } from "./components/Toast";
import Particles from "./components/Particles";

// Layer display names for toast messages
const layerNames = {
  susceptibilityML: "ML Susceptibility",
  susceptibilityDL: "DL Susceptibility",
  hazardFused: "Final Hazard Map",
  runout: "Runout Paths",
  transit: "Transit Zone",
  deposition: "Deposition Zone",
  historicalSusceptibility: "GSI Historical",
  streets: "Street Map",
};

function AppContent() {
  const toast = useToast();

  /* ---------------- GLOBAL STATE ---------------- */

  // Which layers are visible
  const [activeLayers, setActiveLayers] = useState({
    susceptibilityML: false,
    susceptibilityDL: true,
    hazardFused: true,
    runout: true,
    transit: false,
    deposition: false,
    // Historical susceptibility (GSI/KSDMA)
    historicalSusceptibility: false,
    // Streets/OpenStreetMap overlay
    streets: false,
  });

  // Opacity per layer
  const [layerOpacity, setLayerOpacity] = useState({
    susceptibilityML: 0.6,
    susceptibilityDL: 0.7,
    hazardFused: 0.8,
    transit: 0.7,
    deposition: 0.7,
    runout: 1.0,
    historicalSusceptibility: 0.7,
    streets: 1.0,
  });

  // Clicked pixel / location info
  const [selectedPoint, setSelectedPoint] = useState(null);

  // Weather data (from OpenWeather later)
  const [weatherData, setWeatherData] = useState(null);

  // 3D modal toggle (Cesium later)
  const [show3D, setShow3D] = useState(false);

  // Sidebar toggle state
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Selected district for historical susceptibility layer
  const [selectedDistrict, setSelectedDistrict] = useState("all");

  /* ---------------- HANDLERS ---------------- */

  const toggleLayer = useCallback((layerName) => {
    setActiveLayers((prev) => {
      const newState = !prev[layerName];
      // Show toast notification
      const displayName = layerNames[layerName] || layerName;
      if (newState) {
        toast.success(`${displayName} enabled`);
      } else {
        toast.info(`${displayName} disabled`);
      }
      return {
        ...prev,
        [layerName]: newState,
      };
    });
  }, [toast]);

  const changeOpacity = (layer, value) => {
    setLayerOpacity((prev) => ({
      ...prev,
      [layer]: value,
    }));
  };

  const handleMapClick = async ({ lat, lon, type, message }) => {
    // If this is a runout path click, handle it differently
    if (type === "runout") {
      setSelectedPoint({
        type: "runout",
        message: message,
      });
      toast.info("Runout path selected");
      return;
    }
    // Otherwise, try to fetch pixel data from backend (may fail outside raster coverage)
    let normalized = {
      lat: lat,
      lon: lon,
      zone: "Unknown",
      susceptibility: null,
      historicalSusceptibility: null,
      historicalRiskClass: null,
      rainfall: 0,
      riskLevel: null,
    };

    try {
      const res = await fetch(`http://localhost:8000/pixel-info?lat=${lat}&lon=${lon}`);
      if (res.ok) {
        const data = await res.json();
        normalized = {
          lat: data.lat ?? data.latitude ?? lat,
          lon: data.lon ?? data.longitude ?? lon,
          zone: data.zone ?? data.zone_name ?? "Unknown",
          susceptibility: data.susceptibility ?? data.sus ?? null,
          historicalSusceptibility: data.historical_susceptibility ?? null,
          historicalRiskClass: data.historical_risk_class ?? null,
          rainfall: data.rainfall ?? data.rain ?? 0,
          riskLevel: data.riskLevel ?? data.risk_level ?? data.risk ?? null,
        };
        toast.success("Location data loaded");
      } else {
        console.debug("pixel-info returned non-ok status", res.status);
      }
    } catch (err) {
      console.debug("pixel-info request failed (likely outside raster coverage):", err);
    }

    // Always update selected point (with pixel-info if available)
    setSelectedPoint(normalized);

    // Always fetch weather data for the clicked coordinates (global coverage)
    try {
      const weatherRes = await fetch(`http://localhost:8000/weather?lat=${lat}&lon=${lon}`);
      if (weatherRes.ok) {
        const weatherDataFromAPI = await weatherRes.json();
        setWeatherData({
          temp: weatherDataFromAPI.main?.temp,
          description: weatherDataFromAPI.weather?.[0]?.description,
          icon: weatherDataFromAPI.weather?.[0]?.icon,
          humidity: weatherDataFromAPI.main?.humidity,
          windSpeed: weatherDataFromAPI.wind?.speed,
          rainfall: weatherDataFromAPI.rain?.['1h'] || 0,
        });
      } else {
        console.warn("Backend weather proxy returned status", weatherRes.status);
      }
    } catch (weatherErr) {
      console.error("Weather API error:", weatherErr);
    }
  };

  const open3DView = () => {
    setShow3D(true);
    toast.info("Loading 3D terrain view...");
  };

  const close3DView = () => {
    setShow3D(false);
  };

  const toggleSidebar = () => {
    setSidebarOpen((prev) => !prev);
  };

  /* ---------------- UI ---------------- */

  return (
    <div className={`slipsense-app ${sidebarOpen ? "sidebar-open" : "sidebar-closed"}`}>
      {/* Modern Navbar */}
      <Navbar onToggleSidebar={toggleSidebar} sidebarOpen={sidebarOpen} weatherData={weatherData} />

      {/* Content wrapper for sidebar + map */}
      <div className="content-wrapper">
        {/* Side Panel */}
        <motion.aside
          className="side-panel"
          animate={{ x: sidebarOpen ? 0 : -320, opacity: sidebarOpen ? 1 : 0 }}
          transition={{ duration: 0.3, ease: "easeInOut" }}
          pointerEvents={sidebarOpen ? "auto" : "none"}
        >
          {/* Floating particles in sidebar */}
          <Particles count={6} />

          <LayerControl
            activeLayers={activeLayers}
            layerOpacity={layerOpacity}
            onToggle={toggleLayer}
            onOpacityChange={changeOpacity}
            selectedDistrict={selectedDistrict}
            onDistrictChange={setSelectedDistrict}
          />
          <div className="mt-4">
            <Legend />
          </div>

          <AnimatePresence mode="wait">
            {selectedPoint?.type === "runout" && (
              <motion.div
                className="info-box"
                key="runout-info"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
              >
                <h3>Runout Path</h3>
                <p>
                  This line represents the <b>predicted flow direction</b> of a landslide.
                </p>
                <p>
                  It is calculated using the <b>D8 flow direction algorithm</b>, which
                  follows the steepest downhill slope from a failure zone.
                </p>
                <p>
                  Areas intersecting this path are at risk of being impacted even if they
                  are not initiation zones.
                </p>
              </motion.div>
            )}

            {selectedPoint && selectedPoint.type !== "runout" && (
              <motion.div
                className="info-box"
                key="location-info"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
              >
                <h3>Selected Location</h3>
                <p><b>Latitude:</b> {selectedPoint.lat}</p>
                <p><b>Longitude:</b> {selectedPoint.lon}</p>
                <p><b>Zone:</b> {selectedPoint.zone}</p>
                <p><b>DL Susceptibility:</b> {selectedPoint.susceptibility}</p>
                {selectedPoint.historicalRiskClass && (
                  <p><b>GSI Historical:</b> {selectedPoint.historicalRiskClass}</p>
                )}
                <p><b>Rainfall:</b> {selectedPoint.rainfall} mm/hr</p>
                <p><b>Overall Risk:</b> {selectedPoint.riskLevel}</p>

                <button onClick={open3DView}>
                  View 3D Terrain
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.aside>

        {/* Map */}
        <main className="map-container">
          <MapView
            activeLayers={activeLayers}
            layerOpacity={layerOpacity}
            onMapClick={handleMapClick}
            sidebarOpen={sidebarOpen}
            selectedDistrict={selectedDistrict}
          />
        </main>
      </div>

      {/* 3D Modal */}
      <AnimatePresence>
        {show3D && selectedPoint && (
          <CesiumView
            lat={Number(selectedPoint.lat)}
            lon={Number(selectedPoint.lon)}
            onClose={close3DView}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

// Wrap with ToastProvider
function App() {
  return (
    <ToastProvider>
      <AppContent />
    </ToastProvider>
  );
}

export default App;

