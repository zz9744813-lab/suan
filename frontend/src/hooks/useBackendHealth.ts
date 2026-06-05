import { useState, useEffect, useCallback, useRef } from "react";
import { apiBase } from "../api/client";

/**
 * useBackendHealth — polls /health every `intervalMs` ms.
 * Returns { ok, checking, lastCheck, message }.
 *
 * - ok=true   → backend is reachable
 * - ok=false  → backend is down or returned non-200
 * - checking  → a request is in-flight right now
 */
export function useBackendHealth(intervalMs = 15_000) {
  const [ok, setOk] = useState(true);       // assume healthy on first paint
  const [checking, setChecking] = useState(false);
  const [lastCheck, setLastCheck] = useState<Date | null>(null);
  const [message, setMessage] = useState("");
  const timerRef = useRef<ReturnType<typeof setInterval>>();
  const mountedRef = useRef(true);

  const check = useCallback(async () => {
    setChecking(true);
    try {
      const base = apiBase || "";
      const res = await fetch(`${base}/health`, {
        method: "GET",
        signal: AbortSignal.timeout(5_000),
      });
      if (!mountedRef.current) return;
      const json = await res.json();
      const healthy = res.status === 200 && json?.ok === true;
      setOk(healthy);
      setMessage(healthy ? "" : `后端返回 HTTP ${res.status}`);
    } catch (e: any) {
      if (!mountedRef.current) return;
      setOk(false);
      setMessage(
        e?.name === "TimeoutError" || e?.name === "AbortError"
          ? "后端连接超时（5s）"
          : "无法连接后端 — 请检查后端是否启动",
      );
    } finally {
      if (mountedRef.current) {
        setChecking(false);
        setLastCheck(new Date());
      }
    }
  }, []);

  useEffect(() => {
    // first check immediately
    check();
    timerRef.current = setInterval(check, intervalMs);
    return () => {
      mountedRef.current = false;
      clearInterval(timerRef.current);
    };
  }, [check, intervalMs]);

  return { ok, checking, lastCheck, message, recheck: check };
}
