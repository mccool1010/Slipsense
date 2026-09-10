/* global __CESIUM_BASE_URL__ -- injected by vite.config.js `define`, so it exists at
   build time but not as a runtime binding ESLint can see. */
import React, { useEffect, useRef } from "react";
import * as Cesium from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { API_BASE, BACKEND_UNREACHABLE } from "../api";

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

  // Where Cesium fetches its workers, shaders and imagery from at runtime. Defined by
  // vite.config.js: node_modules in development, the copied /cesium/ directory in a
  // production build. Hardcoding the node_modules path meant the deployed 3D view had
  // no workers at all - the requests fell through the SPA rewrite and returned
  // index.html, so Cesium was parsing HTML as JavaScript and as terrain JSON.
  window.CESIUM_BASE_URL =
    typeof __CESIUM_BASE_URL__ !== 'undefined'
      ? __CESIUM_BASE_URL__
      : '/node_modules/cesium/Build/Cesium/';
}

const TILE_SERVER = API_BASE;

// BACKEND_UNREACHABLE is imported from ../api. When a deployed build has no
// VITE_TILE_SERVER it points at localhost, which does not exist for a visitor:
// requesting tiles returns something that is not an image, and Cesium treats a failed
// imagery decode as fatal - "InvalidStateError: The image could not be decoded", then
// "Rendering has stopped", and the globe goes black. The terrain is fine; one
// unreachable overlay takes the scene with it. So the overlay is simply not added.

// Velocity ramp, matching the runout figure: blue slow through red fast. Colouring by
// speed rather than a single hue is what makes the corridors informative - a long slow
// creep and a short violent debris surge are not the same hazard.
function velocityColor(v) {
  const t = Math.max(0, Math.min(1, v / 25));
  return Cesium.Color.fromHsl((1 - t) * 0.6, 0.9, 0.5, 0.9);
}


// Real elevation without a Cesium Ion account.
//
// Ion gates World Terrain and the Photorealistic tiles behind a token, and the
// backend's terrain_tiles/ folder cannot substitute: those are 256x256 8-bit greyscale
// PNGs, while Cesium's heightmap-1.0 expects 65x65 16-bit binary .terrain files, and
// they only go to zoom 4 anyway.
//
// AWS hosts Mapzen/Tilezen terrarium tiles openly, which encode height in RGB:
//     elevation = (R * 256 + G + B / 256) - 32768
// Cesium cannot read that format directly, but CustomHeightmapTerrainProvider accepts
// raw height samples from any source, so decoding them client-side gives genuine 3D
// relief with no credentials.
const TERRARIUM_URL =
  "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";
const HEIGHTMAP_SIZE = 64;

function terrariumTerrainProvider() {
  const canvas = document.createElement("canvas");
  canvas.width = HEIGHTMAP_SIZE;
  canvas.height = HEIGHTMAP_SIZE;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });

  return new Cesium.CustomHeightmapTerrainProvider({
    width: HEIGHTMAP_SIZE,
    height: HEIGHTMAP_SIZE,
    // Terrarium tiles are standard XYZ, so the scheme must be Web Mercator; the
    // Geographic default would sample the wrong tiles entirely.
    tilingScheme: new Cesium.WebMercatorTilingScheme(),
    callback: async (x, y, level) => {
      // Above the dataset's native zoom the request just 404s; returning undefined
      // tells Cesium to upsample the parent rather than leave a hole.
      if (level > 13) return undefined;
      const url = TERRARIUM_URL.replace("{z}", level)
        .replace("{x}", x)
        .replace("{y}", y);
      try {
        const img = await Cesium.Resource.fetchImage({ url, crossOrigin: "anonymous" });
        ctx.clearRect(0, 0, HEIGHTMAP_SIZE, HEIGHTMAP_SIZE);
        ctx.drawImage(img, 0, 0, HEIGHTMAP_SIZE, HEIGHTMAP_SIZE);
        const px = ctx.getImageData(0, 0, HEIGHTMAP_SIZE, HEIGHTMAP_SIZE).data;
        const heights = new Float32Array(HEIGHTMAP_SIZE * HEIGHTMAP_SIZE);
        for (let i = 0; i < heights.length; i += 1) {
          const o = i * 4;
          heights[i] = px[o] * 256 + px[o + 1] + px[o + 2] / 256 - 32768;
        }
        return heights;
      } catch {
        return undefined;
      }
    },
  });
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
        // World terrain and Photorealistic tiles are Ion-hosted and need a token.
        // Without one, fall back to a plain ellipsoid with OSM imagery so the view
        // still renders the susceptibility drape and runout corridors rather than a
        // blank globe - the previous behaviour, which looked like the feature was
        // simply broken.
        const viewer = new Cesium.Viewer(cesiumContainer.current, {
          ...(ION_TOKEN
            ? { terrain: Cesium.Terrain.fromWorldTerrain() }
            : { terrainProvider: terrariumTerrainProvider() }),
          // Satellite imagery either way, matching the 2D map. The previous fallback
          // used OpenStreetMap, which rendered a flat street map and looked nothing
          // like the "3D terrain view" the button promises.
          baseLayer: Cesium.ImageryLayer.fromProviderAsync(
            Promise.resolve(
              new Cesium.UrlTemplateImageryProvider({
                url:
                  "https://server.arcgisonline.com/ArcGIS/rest/services/" +
                  "World_Imagery/MapServer/tile/{z}/{y}/{x}",
                credit: "© Esri",
                maximumLevel: 18,
              })
            )
          ),
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

        // Add Google Photorealistic 3D Tiles (Ion-hosted; skipped without a token)
        try {
          if (!ION_TOKEN) throw new Error("no Ion token configured");
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
        if (BACKEND_UNREACHABLE) {
          console.warn(
            "VITE_TILE_SERVER is not set; skipping the susceptibility drape. " +
            "Terrain and imagery still render."
          );
        } else {
          try {
            const susceptibility = new Cesium.UrlTemplateImageryProvider({
              url: `${TILE_SERVER}/tiles/susceptibility_ml/{z}/{x}/{y}.png`,
              maximumLevel: 14,
              credit: "SlipSense v2 susceptibility",
            });
            const layer = viewer.imageryLayers.addImageryProvider(susceptibility);
            layer.alpha = 0.65;
            // A tile that fails to load must not escalate into a fatal render error.
            if (susceptibility.errorEvent) {
              susceptibility.errorEvent.addEventListener((err) => {
                console.warn("Susceptibility tile failed (continuing):", err?.message);
              });
            }
            console.log("Susceptibility layer draped");
          } catch (layerError) {
            console.warn("Could not drape susceptibility layer:", layerError);
          }
        }

        // Runout corridors, drawn as ground-clamped lines coloured by modelled velocity.
        try {
          if (BACKEND_UNREACHABLE) throw new Error("no backend configured");
          const res = await fetch(
            `${TILE_SERVER}/rasters/v2/runout_paths_exposed.geojson`
          );
          if (res.ok) {
            const geo = await res.json();
            let drawn = 0;
            for (const f of (geo.features || []).slice(0, 250)) {
              const coords = f.geometry?.coordinates || [];
              if (coords.length < 2) continue;
              // Corridors are WGS84 lon/lat, as GeoJSON requires.
              const flat = [];
              for (const [lonDeg, latDeg] of coords) {
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

        // Western Ghats relief is real but subtle beside a 1000 m wide valley; a mild
        // exaggeration makes the slopes that drive failure readable without cartooning.
        viewer.scene.verticalExaggeration = 1.6;

        // Cesium stops the render loop entirely on an unhandled scene error, which
        // turns one failed tile decode into a black screen. Log and carry on instead.
        viewer.scene.renderError.addEventListener((scene, error) => {
          console.warn("Cesium render error (continuing):", error);
          viewer.useDefaultRenderLoop = true;
        });

        viewerRef.current = viewer;
        initialized.current = true;
        console.log("Cesium viewer created successfully");

        // Fly to clicked location
        if (typeof lat === "number" && typeof lon === "number") {
          console.log(`Flying to lat: ${lat}, lon: ${lon}`);
          viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(lon, lat - 0.045, 4500),
            orientation: {
              heading: Cesium.Math.toRadians(0),
              // Oblique, not straight down: a nadir view flattens the terrain and
              // defeats the purpose of opening a 3D view at all.
              pitch: Cesium.Math.toRadians(-35),
              roll: 0,
            },
            duration: 2.2,
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
