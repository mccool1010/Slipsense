import React, { useEffect, useRef } from "react";
import * as Cesium from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";

// Configure Cesium assets path
// The Ion token was previously a string literal in this file, which put a live
// credential into every build and into version control. It now comes from the
// environment; set VITE_CESIUM_ION_TOKEN in frontend/.env (see .env.example).
// The old literal token should be revoked at https://ion.cesium.com/tokens.
const ION_TOKEN = import.meta.env.VITE_CESIUM_ION_TOKEN;

if (typeof window !== 'undefined') {
  if (ION_TOKEN) {
    Cesium.Ion.defaultAccessToken = ION_TOKEN;
  } else {
    console.warn(
      "VITE_CESIUM_ION_TOKEN is not set - world terrain and Photorealistic 3D Tiles " +
      "will not load. Copy frontend/.env.example to .env and add your Ion token."
    );
  }

  // Set the correct asset path for Cesium
  window.CESIUM_BASE_URL = '/node_modules/cesium/Build/Cesium/';
}

const TILE_SERVER = import.meta.env.VITE_TILE_SERVER || "http://localhost:8000";

// Velocity ramp, matching the runout figure: blue slow through red fast. Colouring by
// speed rather than a single hue is what makes the corridors informative - a long slow
// creep and a short violent debris surge are not the same hazard.
function velocityColor(v) {
  const t = Math.max(0, Math.min(1, v / 25));
  return Cesium.Color.fromHsl((1 - t) * 0.6, 0.9, 0.5, 0.9);
}

// runout_paths.geojson carries EPSG:32643 metres, not degrees, because it is written
// alongside the rasters. Cesium needs degrees, so convert with the inverse UTM 43N
// formulae rather than pulling in a projection library for one transform.
async function buildProjector(geo) {
  const name = geo?.crs?.properties?.name || "";
  if (name.includes("4326")) return (x, y) => [x, y];

  const k0 = 0.9996, a = 6378137.0, e = 0.081819191;
  const e1sq = 0.006739497, falseEasting = 500000.0, lon0 = 75.0;
  return (x, y) => {
    const m = y / k0;
    const mu = m / (a * (1 - e * e / 4 - (3 * e ** 4) / 64 - (5 * e ** 6) / 256));
    const e1 = (1 - Math.sqrt(1 - e * e)) / (1 + Math.sqrt(1 - e * e));
    const phi1 =
      mu +
      ((3 * e1) / 2 - (27 * e1 ** 3) / 32) * Math.sin(2 * mu) +
      ((21 * e1 ** 2) / 16 - (55 * e1 ** 4) / 32) * Math.sin(4 * mu) +
      ((151 * e1 ** 3) / 96) * Math.sin(6 * mu);
    const n = a / Math.sqrt(1 - (e * Math.sin(phi1)) ** 2);
    const t = Math.tan(phi1) ** 2;
    const c = e1sq * Math.cos(phi1) ** 2;
    const r = (a * (1 - e * e)) / Math.pow(1 - (e * Math.sin(phi1)) ** 2, 1.5);
    const d = (x - falseEasting) / (n * k0);
    const lat =
      phi1 -
      ((n * Math.tan(phi1)) / r) *
        ((d * d) / 2 -
          ((5 + 3 * t + 10 * c - 4 * c * c - 9 * e1sq) * d ** 4) / 24 +
          ((61 + 90 * t + 298 * c + 45 * t * t - 252 * e1sq - 3 * c * c) * d ** 6) / 720);
    const lon =
      (d -
        ((1 + 2 * t + c) * d ** 3) / 6 +
        ((5 - 2 * c + 28 * t - 3 * c * c + 8 * e1sq + 24 * t * t) * d ** 5) / 120) /
      Math.cos(phi1);
    return [lon0 + (lon * 180) / Math.PI, (lat * 180) / Math.PI];
  };
}

const CesiumView = ({ lat, lon, onClose }) => {
  const cesiumContainer = useRef(null);
  const viewerRef = useRef(null);
  const initialized = useRef(false);

  useEffect(() => {
    if (!cesiumContainer.current || initialized.current) return;

    const initViewer = async () => {
      try {
        console.log("Initializing Cesium viewer with Google Photorealistic 3D Tiles...");

        // Destroy previous viewer if it exists
        if (viewerRef.current && !viewerRef.current.isDestroyed()) {
          viewerRef.current.destroy();
          viewerRef.current = null;
        }

        // Clear the container
        cesiumContainer.current.innerHTML = '';

        // Create viewer with Google Photorealistic 3D Tiles
        const viewer = new Cesium.Viewer(cesiumContainer.current, {
          terrain: Cesium.Terrain.fromWorldTerrain(),
          timeline: false,
          animation: false,
          baseLayerPicker: false,
          geocoder: false,
          homeButton: false,
          sceneModePicker: false,
          navigationHelpButton: false,
          fullscreenButton: false,
          requestRenderMode: false,
        });

        // Add Google Photorealistic 3D Tiles
        try {
          const googlePhotorealistic3dTileset = await Cesium.Cesium3DTileset.fromUrl(
            Cesium.IonResource.fromAssetId(2275207),
            {
              maximumScreenSpaceError: 128,
              skipLevelOfDetail: true,
            }
          );
          viewer.scene.primitives.add(googlePhotorealistic3dTileset);
          console.log("Google Photorealistic 3D Tiles loaded successfully");
        } catch (tilesetError) {
          console.warn("Could not load Google Photorealistic tiles:", tilesetError);
        }

        // Drape the susceptibility map over the terrain. Landslides are a
        // three-dimensional phenomenon and a top-down view hides the relief that drives
        // them; seen obliquely, the high-susceptibility bands sit visibly on the steep
        // flanks rather than floating as abstract colour.
        try {
          const susceptibility = new Cesium.UrlTemplateImageryProvider({
            url: `${TILE_SERVER}/tiles/susceptibility_ml/{z}/{x}/{y}.png`,
            maximumLevel: 14,
            credit: "SlipSense v2 susceptibility",
          });
          const layer = viewer.imageryLayers.addImageryProvider(susceptibility);
          layer.alpha = 0.65;
          console.log("Susceptibility layer draped");
        } catch (layerError) {
          console.warn("Could not drape susceptibility layer:", layerError);
        }

        // Runout corridors, drawn as ground-clamped lines coloured by modelled velocity.
        try {
          const res = await fetch(`${TILE_SERVER}/rasters/runout_paths.geojson`);
          if (res.ok) {
            const geo = await res.json();
            const toDeg = await buildProjector(geo);
            let drawn = 0;
            for (const f of (geo.features || []).slice(0, 250)) {
              const coords = f.geometry?.coordinates || [];
              if (coords.length < 2) continue;
              const flat = [];
              for (const [x, y] of coords) {
                const [lonDeg, latDeg] = toDeg(x, y);
                flat.push(lonDeg, latDeg);
              }
              const v = f.properties?.max_velocity_ms ?? 0;
              viewer.entities.add({
                polyline: {
                  positions: Cesium.Cartesian3.fromDegreesArray(flat),
                  width: 3,
                  clampToGround: true,
                  material: velocityColor(v),
                },
                description:
                  `Length ${f.properties?.length_m ?? "?"} m<br/>` +
                  `Drop ${f.properties?.drop_m ?? "?"} m<br/>` +
                  `Max velocity ${v} m/s`,
              });
              drawn += 1;
            }
            console.log(`Runout corridors drawn: ${drawn}`);
          }
        } catch (runoutError) {
          console.warn("Could not load runout corridors:", runoutError);
        }

        viewerRef.current = viewer;
        initialized.current = true;
        console.log("Cesium viewer created successfully");

        // Fly to clicked location
        if (typeof lat === "number" && typeof lon === "number") {
          console.log(`Flying to lat: ${lat}, lon: ${lon}`);
          viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(lon, lat, 2000),
            duration: 1.8,
          });
        }

        return viewer;
      } catch (err) {
        console.error("Error initializing Cesium viewer:", err);
        if (cesiumContainer.current) {
          cesiumContainer.current.innerHTML = `<div style="color: red; padding: 20px; background: white;">Error: ${err.message}</div>`;
        }
      }
    };

    initViewer();

    return () => {
      try {
        if (viewerRef.current && !viewerRef.current.isDestroyed()) {
          viewerRef.current.destroy();
          viewerRef.current = null;
          initialized.current = false;
        }
      } catch (e) {
        console.error("Error destroying viewer:", e);
      }
    };
  }, []);

  return (
    <div className="cesium-wrapper">
      <button className="close-btn" onClick={onClose}>✖</button>
      <div ref={cesiumContainer} className="cesium-container" />
    </div>
  );
};

export default CesiumView;
