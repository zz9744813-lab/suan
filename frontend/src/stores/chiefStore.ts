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
      // Build the new messages list BEFORE touching the session.
      // We do this in one place so we can branch on "is this a
      // brand-new session" without racing against startSession's
      // loadMessages() call.
      const userEcho = {
        id: -Date.now(),
        session_id: reply.session_id,
        role: "user" as const,
        content: msg,
        actions: null,
        thinking: null,
        tokens_in: 0,
        tokens_out: 0,
        cost_usd: 0,
        created_at: new Date().toISOString(),
      };
      const newMessages = [...get().messages, userEcho, reply];

      // P0-CHIEF-2 / R16 fix: DO NOT call startSession() here when
      // the chat just created a fresh session. startSession() wipes
      // the local messages to [] then awaits loadMessages() — but
      // loadMessages() will return the [user, chief] we just sent,
      // and THEN we appended [user, chief] AGAIN below the
      // startSession() call. Net effect: every fresh-session first
      // message gets a double echo (the chief reply appears twice).
      //
      // We just set the session in-place and use the messages we
      // already built. Existing sessions take the normal "append"
      // path.
      if (!get().session) {
        set({
          session: {
            id: reply.session_id,
            title: msg.slice(0, 30) || "新会话",
            project_id: projectId ?? null,
            page_context: null,
            created_at: reply.created_at,
          },
          messages: newMessages,
        });
      } else {
        set({ messages: newMessages });
      }
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
