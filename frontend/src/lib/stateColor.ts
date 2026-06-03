/**
 * Worker state → semantic color used by the rail dot, the
 * project library dot, and the status bar dot. Centralised so
 * the three places stay in sync.
 */
export type StateColor = "ok" | "warn" | "error" | "info";

export function stateColor(state: string | null | undefined): StateColor {
  if (state === "running") return "ok";
  if (state === "paused" || state === "paused_budget") return "warn";
  if (state === "error" || state === "stopped") return "error";
  return "info";
}
