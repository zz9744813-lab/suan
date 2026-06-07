import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles/tokens.css";
import "./styles/global.css";
import "./styles/accessibility.css";

// R17: read the persisted theme from localStorage BEFORE React mounts
// so the very first paint already has the right `data-theme` on
// <html>. Without this, a dark-mode user would briefly see the
// light palette (FOUC) before the AppShell effect kicks in.
(function applyInitialTheme() {
  try {
    const raw = localStorage.getItem("noverlforge.layout.v3");
    if (raw) {
      const parsed = JSON.parse(raw);
      const theme = parsed?.state?.theme;
      if (theme === "dark" || theme === "light") {
        document.documentElement.dataset.theme = theme;
      }
    }
  } catch {
    // Ignore — fallback to CSS default (light).
  }
})();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
