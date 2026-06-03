/// <reference types="vite/client" />

// P0-MODEL-9: optional override for the backend base URL. Set in
// ``.env.development`` to bypass Vite's dev proxy (which drops
// PUT/POST request bodies — see client.ts for the long version).
interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
