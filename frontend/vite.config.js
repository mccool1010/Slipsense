import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'

// Cesium ships its workers, shaders, fonts and imagery as static files that it fetches
// at runtime from CESIUM_BASE_URL. In development that could point straight at
// node_modules because Vite serves it, but a production bundle has no node_modules -
// and with an SPA rewrite in front, every one of those requests returns index.html
// instead of a 404. Cesium then tries to parse HTML as a worker script and as terrain
// JSON, which surfaces as:
//
//   Loading Worker from ".../Workers/createVerticesFromQuantizedTerrainMesh.js" was
//   blocked because of a disallowed MIME type ("text/html")
//   SyntaxError: JSON.parse: unexpected character at line 1 column 1
//   InvalidStateError: The image could not be decoded
//
// None of which mentions the actual problem. So the assets are copied into the build
// output and CESIUM_BASE_URL points there instead.
const CESIUM_STATIC_DIRS = ['Assets', 'ThirdParty', 'Widgets', 'Workers']

function copyCesiumAssets() {
  return {
    name: 'copy-cesium-assets',
    apply: 'build',
    closeBundle() {
      const from = path.join('node_modules', 'cesium', 'Build', 'Cesium')
      const to = path.join('dist', 'cesium')
      if (!fs.existsSync(from)) {
        this.warn(`Cesium build assets not found at ${from}; the 3D view will not load.`)
        return
      }
      fs.mkdirSync(to, { recursive: true })
      for (const dir of CESIUM_STATIC_DIRS) {
        const src = path.join(from, dir)
        if (fs.existsSync(src)) {
          fs.cpSync(src, path.join(to, dir), { recursive: true })
        }
      }
    },
  }
}

export default defineConfig({
  plugins: [react(), copyCesiumAssets()],
  define: {
    // Read by src/components/CesiumView.jsx. Dev can serve straight from node_modules;
    // production reads the copy made above.
    __CESIUM_BASE_URL__: JSON.stringify(
      process.env.NODE_ENV === 'production'
        ? '/cesium/'
        : '/node_modules/cesium/Build/Cesium/'
    ),
  },
  optimizeDeps: {
    include: ['cesium'],
  },
  server: {
    fs: {
      allow: ['.'],
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          cesium: ['cesium'],
        },
      },
    },
  },
})
