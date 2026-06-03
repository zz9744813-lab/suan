import type { APIResponse } from "../types";

// All API paths are prefixed with /api on the backend.
//
// P0-MODEL-9: the frontend talks to the backend directly, not
// through Vite's dev proxy. Vite's proxy uses ``http-proxy`` and
// does not re-stream PUT/POST request bodies — the
// ``Content-Length`` header still matches the original request
// while the body is dropped, and the FastAPI backend replies
// ``{"detail":"There was an error parsing the body"}`` with HTTP
// 400. That is what made the 「编辑 Provider」 button look
// unresponsive (the user clicks 保存, nothing changes, no error
// toast in the obvious spot).
//
// Production still runs behind nginx which proxies the body
// correctly, so the empty string fallback (relative path) is
// the right default for prod. In dev (``npm run dev``), set
// ``VITE_API_BASE=http://127.0.0.1:8000`` in ``frontend/.env``
// (or pass it inline) to bypass Vite's broken PUT-body handling.
const BASE = (import.meta.env.VITE_API_BASE ?? "") as string;

// One-line startup banner so the operator can see at a glance
// whether the dev server is talking to the backend directly (good,
// "通过 VITE_API_BASE 直连") or going through Vite's broken PUT
// proxy (bad, "走相对路径会触发 body 丢失"). Logged once on the
// very first API call so we don't spam the console.
let _bannerLogged = false;
function logBaseOnce() {
  if (_bannerLogged) return;
  _bannerLogged = true;
  if (BASE) {
    // eslint-disable-next-line no-console
    console.info(`[api] backend base = ${BASE} (直连，绕过 Vite dev proxy)`);
  } else {
    // eslint-disable-next-line no-console
    console.warn(`[api] backend base = (relative) — dev 模式下走 Vite proxy，PUT body 会被丢弃！请在 frontend/.env.development 中设置 VITE_API_BASE=http://127.0.0.1:8000`);
  }
}

// Default fetch timeout. Long-running endpoints (the model
// ``health-check`` runs 4 probes that can take ~60-90s on slow
// providers) override this per-call. Without a timeout at all, a
// stuck backend would freeze the UI's buttons (no loading state) and
// the browser tab would dim, looking like a "black screen".
const DEFAULT_TIMEOUT_MS = 60_000;

async function request<T>(
  method: string,
  path: string,
  body?: any,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  logBaseOnce();
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  const opts: RequestInit = {
    method,
    headers: { "Content-Type": "application/json; charset=utf-8" },
    signal: ctrl.signal,
  };
  if (body !== undefined) {
    opts.body = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(BASE + path, opts);
  } catch (e: any) {
    clearTimeout(timer);
    if (e?.name === "AbortError") {
      throw new Error(`请求超时（>${Math.round(timeoutMs / 1000)}s），后端可能卡在某个慢调用上。`);
    }
    throw e;
  }
  clearTimeout(timer);
  // P0-MODEL-6 fix: HTTP errors come back in two shapes.
  //   1. Unified APIError envelope ``{"ok": false, "error": {type, message, suggestion, details}}``
  //      — produced by the custom ``APIError`` in ``app/core/errors.py``.
  //   2. FastAPI default ``{"detail": [...]}`` — produced by
  //      ``RequestValidationError`` (HTTP 422) and any unhandled
  //      ``HTTPException`` that doesn't go through ``APIError``.
  // The old code only handled shape (1) and rendered shape (2) as
  // a useless ``"HTTP 422"`` string, hiding the per-field reason.
  let json: any;
  try {
    json = await res.json();
  } catch (e) {
    throw new Error(`非 JSON 响应: HTTP ${res.status}`);
  }
  if (res.status >= 400) {
    const wrapped: any = new Error(`HTTP ${res.status} ${res.statusText || ""}`.trim());
    wrapped.status = res.status;
    if (json && typeof json === "object") {
      // shape 1: unified envelope
      if (json.error) {
        const err = json.error;
        wrapped.message = err.message
          ? `${err.type || "Error"}: ${err.message}${err.suggestion ? `（${err.suggestion}）` : ""}`
          : wrapped.message;
        wrapped.errorType = err.type;
        wrapped.suggestion = err.suggestion;
        wrapped.details = err.details ?? {};
        // shape 1 also nests pydantic 422 items under ``err.details``
        // or as ``err.detail``. Normalise to ``wrapped.detail``.
        if (Array.isArray(err.detail)) wrapped.detail = err.detail;
      }
      // shape 2: FastAPI default
      if (Array.isArray(json.detail)) {
        wrapped.detail = json.detail;
        // Build a one-line summary: "field: msg; field2: msg2"
        const summary = (json.detail as any[])
          .map((d) => {
            const loc = Array.isArray(d?.loc) ? d.loc.filter((l: any) => l !== "body").join(".") : "?";
            return `${loc || "?"}: ${d?.msg ?? "校验失败"}`;
          })
          .join("\n");
        wrapped.message = summary || wrapped.message;
        // Also expose as details for the UI's per-field renderer.
        const details: Record<string, string> = {};
        for (const d of json.detail as any[]) {
          const loc = Array.isArray(d?.loc) ? d.loc.filter((l: any) => l !== "body").join(".") : "?";
          if (loc) details[loc] = d?.msg ?? "校验失败";
        }
        wrapped.details = details;
      }
    }
    throw wrapped;
  }
  return (json?.data ?? json) as T;
}

export const api = {
  get: <T,>(path: string) => request<T>("GET", path),
  post: <T,>(path: string, body?: any, timeoutMs?: number) => request<T>("POST", path, body ?? {}, timeoutMs),
  put: <T,>(path: string, body?: any, timeoutMs?: number) => request<T>("PUT", path, body ?? {}, timeoutMs),
  patch: <T,>(path: string, body?: any, timeoutMs?: number) => request<T>("PATCH", path, body ?? {}, timeoutMs),
  delete: <T,>(path: string, timeoutMs?: number) => request<T>("DELETE", path, undefined, timeoutMs),
};

export const apiBase = BASE;
