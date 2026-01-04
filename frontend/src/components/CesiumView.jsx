import React, { useEffect, useRef } from "react";
import * as Cesium from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";

// Configure Cesium assets path
if (typeof window !== 'undefined') {
  Cesium.Ion.defaultAccessToken =
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJiZmY2ZWJlYy01NzFhLTQ4YzQtOTgxNC00NDk3OWM0MWJlMmYiLCJpZCI6MzY5OTIxLCJpYXQiOjE3NjU4MjEyMTR9.AFh_u_53RSIC_9bDmqRzYMgS3pAJlwNmjvQ5XakUctE";
  
  // Set the correct asset path for Cesium
  window.CESIUM_BASE_URL = '/node_modules/cesium/Build/Cesium/';
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
