import { create } from "zustand";
import type { ChiefAgentMessage, ChiefAgentSession } from "../types";
import { chiefChat, listChiefMessages } from "../api";

type State = {
  session: ChiefAgentSession | null;
  messages: ChiefAgentMessage[];
  loading: boolean;
  streaming: boolean;
};

type Actions = {
  startSession: (s: ChiefAgentSession | null) => Promise<void>;
  loadMessages: () => Promise<void>;
  send: (msg: string, projectId?: number) => Promise<void>;
  reset: () => void;
};

export const useChiefStore = create<State & Actions>((set, get) => ({
  session: null,
  messages: [],
  loading: false,
  streaming: false,

  startSession: async (s) => {
    set({ session: s, messages: [], loading: false });
    if (s) await get().loadMessages();
  },

  loadMessages: async () => {
    const s = get().session;
    if (!s) return;
    set({ loading: true });
    try {
      const messages = await listChiefMessages(s.id);
      set({ messages, loading: false });
    } catch (e) {
      set({ loading: false });
    }
  },

  send: async (msg, projectId) => {
    if (!msg.trim()) return;
    set({ streaming: true });
    try {
      const sid = get().session?.id;
      const reply = await chiefChat({
        session_id: sid,
        project_id: projectId,
        message: msg,
      });
      // session is created on the backend if it didn't exist
      if (!get().session) {
        // refresh the new session
        await get().startSession({
          id: reply.session_id,
          title: msg.slice(0, 30) || "新会话",
          project_id: projectId ?? null,
          page_context: null,
          created_at: reply.created_at,
        });
      }
      // append both user echo (synthesized) and the chief reply
      set({
        messages: [
          ...get().messages,
          {
            id: -Date.now(),
            session_id: reply.session_id,
            role: "user",
            content: msg,
            actions: null,
            thinking: null,
            tokens_in: 0,
            tokens_out: 0,
            cost_usd: 0,
            created_at: new Date().toISOString(),
          },
          reply,
        ],
      });
    } catch (e: any) {
      set({
        messages: [
          ...get().messages,
          {
            id: -Date.now(),
            session_id: 0,
            role: "chief",
            content: `调用失败：${e.message ?? e}`,
            actions: null,
            thinking: null,
            tokens_in: 0,
            tokens_out: 0,
            cost_usd: 0,
            created_at: new Date().toISOString(),
          },
        ],
      });
    } finally {
      set({ streaming: false });
    }
  },

  reset: () => set({ session: null, messages: [] }),
}));
