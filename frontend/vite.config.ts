import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: "127.0.0.1",
    // NOTE on CORS / proxy:
    // We deliberately do NOT proxy ``/api`` through Vite. Vite's
    // dev proxy uses ``http-proxy`` and does not re-stream PUT/POST
    // request bodies — the ``Content-Length`` header still matches
    // the original request while the body is dropped, and the
    // FastAPI backend replies ``{"detail":"There was an error parsing
    // the body"}`` with HTTP 400. That is what made the
    // 「编辑 Provider」 button look unresponsive.
    //
    // Instead, the frontend talks to the backend directly on
    // ``VITE_API_BASE`` (default ``http://127.0.0.1:8000``) and
    // CORS at the backend (``app/core/config.py`` -> ``cors_origins``)
    // whitelists this dev origin. Production runs behind nginx which
    // does proxy the body correctly.
  },
});



