import { create } from "zustand";

export type LiveEvent = {
  id: number;
  event_type: string;
  level: string;
  message: string;
  project_id: number | null;
  chapter_id: number | null;
  task_id: number | null;
  ts: number;
  data?: Record<string, any> | null;
};

type State = {
  connected: boolean;
  events: LiveEvent[];
  maxEvents: number;
};

type Actions = {
  push: (e: LiveEvent) => void;
  setConnected: (c: boolean) => void;
  clear: () => void;
};

let counter = 0;

/**
 * P1-UI-6 fix: event types that exist only to keep the SSE
 * connection alive. They have no informational value for the user
 * and previously crowded out real events (task.failed, etc.).
 * Connection state is surfaced separately via the ``connected`` flag.
 */
const HIDDEN_EVENT_TYPES = new Set<string>([
  "sse.heartbeat",
  "sse.connected", // status mirrors the ``connected`` flag in the store
  "app.ready",     // noisy on every reconnect
]);

export const useEventStore = create<State & Actions>((set, get) => ({
  connected: false,
  events: [],
  maxEvents: 200,

  push: (e) => {
    if (HIDDEN_EVENT_TYPES.has(e.event_type)) return;
    const ev = { ...e, id: e.id || ++counter };
    const events = get().events.concat(ev);
    if (events.length > get().maxEvents) {
      events.splice(0, events.length - get().maxEvents);
    }
    set({ events });
  },

  setConnected: (c) => set({ connected: c }),

  clear: () => set({ events: [] }),
}));
