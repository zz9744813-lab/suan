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

export const useEventStore = create<State & Actions>((set, get) => ({
  connected: false,
  events: [],
  maxEvents: 200,

  push: (e) => {
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
