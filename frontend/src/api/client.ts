import type { APIResponse } from "../types";

// All API paths are prefixed with /api on the backend.
const BASE = ""; // Vite dev server proxies /api to the backend.

async function request<T>(
  method: string,
  path: string,
  body?: any
): Promise<T> {
  const opts: RequestInit = {
    method,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  };
  if (body !== undefined) {
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(BASE + path, opts);
  let json: APIResponse<T>;
  try {
    json = await res.json();
  } catch (e) {
    throw new Error(`非 JSON 响应: HTTP ${res.status}`);
  }
  if (!json.ok) {
    const err = json.error;
    const msg = err
      ? `${err.type}: ${err.message}${err.suggestion ? `（${err.suggestion}）` : ""}`
      : `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return json.data as T;
}

export const api = {
  get: <T,>(path: string) => request<T>("GET", path),
  post: <T,>(path: string, body?: any) => request<T>("POST", path, body ?? {}),
  put: <T,>(path: string, body?: any) => request<T>("PUT", path, body ?? {}),
  patch: <T,>(path: string, body?: any) => request<T>("PATCH", path, body ?? {}),
  delete: <T,>(path: string) => request<T>("DELETE", path),
};

export const apiBase = BASE;
