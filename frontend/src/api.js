/**
 * Backend base URL, in one place.
 *
 * This was duplicated across four files, and only two of them read the environment
 * variable. The deployed site therefore worked for tiles, bounds and hover while the
 * weather panel, the click handler and the alert panel each called
 * http://localhost:8000 - which for a visitor is their own machine, so those requests
 * failed CORS while everything else looked fine. A partially-configured backend is
 * harder to diagnose than a wholly missing one, precisely because most of the app works.
 *
 * Vite inlines VITE_* at build time, so changing it in the hosting dashboard requires a
 * rebuild, not just a restart.
 */
export const API_BASE =
  import.meta.env.VITE_TILE_SERVER || "http://localhost:8000";

/** True when a deployed build is still pointing at localhost, i.e. misconfigured. */
export const BACKEND_UNREACHABLE =
  typeof window !== "undefined" &&
  !/^(localhost|127\.0\.0\.1|\[::1\])$/.test(window.location.hostname) &&
  /localhost|127\.0\.0\.1/.test(API_BASE);

/** Build a URL against the backend. */
export const api = (path) => `${API_BASE}${path}`;
