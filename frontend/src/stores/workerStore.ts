import { create } from "zustand";
import type { WorkerStatus } from "../types";
import { workerStatus as fetchStatus } from "../api";

type State = {
  status: WorkerStatus | null;
  loading: boolean;
  lastRefresh: number;
  pollHandle: number | null;
};

type Actions = {
  refresh: () => Promise<void>;
  startPolling: () => void;
  stopPolling: () => void;
};

export const useWorkerStore = create<State & Actions>((set, get) => ({
  status: null,
  loading: false,
  lastRefresh: 0,
  pollHandle: null,

  refresh: async () => {
    try {
      const status = await fetchStatus();
      set({ status, lastRefresh: Date.now() });
    } catch (e) {
      // swallow during polling; errors are surfaced elsewhere
    }
  },

  startPolling: () => {
    const existing = get().pollHandle;
    if (existing) return;
    get().refresh();
    const h = window.setInterval(() => get().refresh(), 2500);
    set({ pollHandle: h });
  },

  stopPolling: () => {
    const h = get().pollHandle;
    if (h) {
      window.clearInterval(h);
      set({ pollHandle: null });
    }
  },
}));
