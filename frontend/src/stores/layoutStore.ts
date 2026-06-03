import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * AppShell layout state (P0-UI-1, P0-UI-4).
 *
 * Two sidebars can be in three states each:
 *   - expanded: full width, full content
 *   - compact : narrow rail (icons / status dot only)
 *   - hidden  : zero width, main content takes the space
 *
 * R17 adds the `theme` field (light / dark) — toggled by the rail
 * button and persisted to localStorage so the user's choice survives
 * reloads. The actual CSS variables are overridden in tokens.css
 * under `:root[data-theme="dark"]`; AppShell.tsx writes that data
 * attribute onto <html> whenever the value changes.
 *
 * Persisted to localStorage so the user's preferences survive reloads.
 * No SSR concerns here (Vite SPA), so a straight `persist` is fine.
 */
export type PanelMode = "expanded" | "compact" | "hidden";
export type ThemeMode = "light" | "dark";

type State = {
  projectNavMode: PanelMode;
  chiefPanelMode: PanelMode;
  theme: ThemeMode;
};

type Actions = {
  setProjectNavMode: (mode: PanelMode) => void;
  setChiefPanelMode: (mode: PanelMode) => void;
  toggleProjectNav: () => void;
  toggleChiefPanel: () => void;
  cycleProjectNav: () => void;
  cycleChiefPanel: () => void;
  setTheme: (t: ThemeMode) => void;
  toggleTheme: () => void;
};

/**
 * 状态循环：expanded → compact → hidden → expanded
 * 比三个独立按钮更省 UI 空间，又能让用户逐步收窄而不是直接消失。
 */
function cycle(mode: PanelMode): PanelMode {
  if (mode === "expanded") return "compact";
  if (mode === "compact") return "hidden";
  return "expanded";
}

export const useLayoutStore = create<State & Actions>()(
  persist(
    (set, get) => ({
      // R16 / P0-UI-8: project nav default flipped to "hidden".
      // The expanded sidebar took 1/4 of the screen for project
      // listing when the rail already has a compact avatar strip
      // AND /projects route handles full project management. Users
      // who want the inline list can still cycle to it via the
      // toggle button (now opt-in instead of opt-out).
      projectNavMode: "hidden",
      chiefPanelMode: "expanded",
      // R17: default to light. The dark mode is a toggle the user
      // actively picks; the bright Concept-B palette was the
      // original design intent and we don't want to surprise users
      // who reload after a long absence.
      theme: "light",
      setProjectNavMode: (mode) => set({ projectNavMode: mode }),
      setChiefPanelMode: (mode) => set({ chiefPanelMode: mode }),
      toggleProjectNav: () =>
        set({ projectNavMode: get().projectNavMode === "hidden" ? "expanded" : "hidden" }),
      toggleChiefPanel: () =>
        set({ chiefPanelMode: get().chiefPanelMode === "hidden" ? "expanded" : "hidden" }),
      cycleProjectNav: () => set({ projectNavMode: cycle(get().projectNavMode) }),
      cycleChiefPanel: () => set({ chiefPanelMode: cycle(get().chiefPanelMode) }),
      setTheme: (t) => set({ theme: t }),
      toggleTheme: () => set({ theme: get().theme === "dark" ? "light" : "dark" }),
    }),
    {
      // Bumped the storage key so users on the old "expanded"
      // default get the new "hidden" default on next visit,
      // instead of being stuck with their old persisted value.
      name: "noverlforge.layout.v3",
      version: 3,
      migrate: (persisted: any, _v: number) => {
        // v1 → v2: force project nav to hidden on upgrade
        // v2 → v3: add theme (default to light, preserve everything else)
        if (persisted && typeof persisted === "object") {
          return {
            ...persisted,
            projectNavMode: "hidden",
            theme: persisted.theme ?? "light",
          };
        }
        return persisted;
      },
    }
  )
);
