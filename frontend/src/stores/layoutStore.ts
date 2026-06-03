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
 * Persisted to localStorage so the user's preferences survive reloads.
 * No SSR concerns here (Vite SPA), so a straight `persist` is fine.
 */
export type PanelMode = "expanded" | "compact" | "hidden";

type State = {
  projectNavMode: PanelMode;
  chiefPanelMode: PanelMode;
};

type Actions = {
  setProjectNavMode: (mode: PanelMode) => void;
  setChiefPanelMode: (mode: PanelMode) => void;
  toggleProjectNav: () => void;
  toggleChiefPanel: () => void;
  cycleProjectNav: () => void;
  cycleChiefPanel: () => void;
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
      projectNavMode: "expanded",
      chiefPanelMode: "expanded",
      setProjectNavMode: (mode) => set({ projectNavMode: mode }),
      setChiefPanelMode: (mode) => set({ chiefPanelMode: mode }),
      toggleProjectNav: () =>
        set({ projectNavMode: get().projectNavMode === "hidden" ? "expanded" : "hidden" }),
      toggleChiefPanel: () =>
        set({ chiefPanelMode: get().chiefPanelMode === "hidden" ? "expanded" : "hidden" }),
      cycleProjectNav: () => set({ projectNavMode: cycle(get().projectNavMode) }),
      cycleChiefPanel: () => set({ chiefPanelMode: cycle(get().chiefPanelMode) }),
    }),
    {
      name: "noverlforge.layout.v1",
      version: 1,
    }
  )
);
