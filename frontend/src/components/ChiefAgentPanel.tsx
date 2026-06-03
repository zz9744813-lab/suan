import { useEffect, useRef, useState } from "react";
import { useChiefStore } from "../stores/chiefStore";
import { confirmChiefAction, createChiefSession, listChiefSessions } from "../api";

type Props = { projectId: number | null };

// 右侧常驻的总编调度面板（spec §5.4 / §17.1）
// 形态：会话列表 + 当前消息流 + 输入框 + 操作卡片
export function ChiefAgentPanel({ projectId }: Props) {
  const session = useChiefStore((s) => s.session);
  const messages = useChiefStore((s) => s.messages);
  const streaming = useChiefStore((s) => s.streaming);
  const startSession = useChiefStore((s) => s.startSession);
  const send = useChiefStore((s) => s.send);
  const [input, setInput] = useState("");
  const [sessionList, setSessionList] = useState<any[]>([]);
  const [actionFeedback, setActionFeedback] = useState<{ id: string; msg: string; ok: boolean } | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streaming]);

  useEffect(() => {
    listChiefSessions(projectId ?? undefined).then(setSessionList).catch(() => {});
  }, [projectId, session]);

  const onSend = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    await send(text, projectId ?? undefined);
    listChiefSessions(projectId ?? undefined).then(setSessionList).catch(() => {});
  };

  const onNewSession = async () => {
    const s = await createChiefSession({
      title: "新会话",
      project_id: projectId ?? undefined,
      page_context: "chief-agent-panel",
    });
    await startSession(s);
    listChiefSessions(projectId ?? undefined).then(setSessionList).catch(() => {});
  };

  const onPickSession = async (sid: number) => {
    const s = sessionList.find((x) => x.id === sid);
    if (s) await startSession(s);
  };

  const onAction = async (actionId: string, actionType: string, params: any) => {
    setActionFeedback(null);
    try {
      const res = await confirmChiefAction(actionId, {
        action_type: actionType,
        params,
        project_id: projectId,
      });
      setActionFeedback({ id: actionId, msg: `已执行：${res.data?.action ?? actionType}`, ok: true });
    } catch (e: any) {
      setActionFeedback({ id: actionId, msg: e.message ?? String(e), ok: false });
    }
  };

  return (
    <aside className="chief-panel">
      <div className="chief-header">
        <div className="chief-avatar">总</div>
        <div>
          <div className="chief-title">总编</div>
          <div className="chief-role">主编 + 调度器</div>
        </div>
        <span className="spacer" />
        <button className="new-btn" onClick={onNewSession}>+ 新会话</button>
      </div>

      <div className="chief-sessions-bar">
        {sessionList.length === 0 ? (
          <span>还没有会话</span>
        ) : (
          <>
            <span>会话：</span>
            {sessionList.slice(0, 6).map((s) => (
              <button
                key={s.id}
                className={`pill ${s.id === session?.id ? "" : ""}`}
                onClick={() => onPickSession(s.id)}
                style={{
                  cursor: "pointer",
                  borderColor: s.id === session?.id ? "var(--accent-gold)" : undefined,
                  color: s.id === session?.id ? "var(--accent-gold)" : undefined,
                }}
              >
                {s.title.slice(0, 12)}
              </button>
            ))}
          </>
        )}
      </div>

      <div className="chief-messages" ref={scrollRef}>
        {messages.length === 0 && !streaming && (
          <div className="page-empty" style={{ padding: 40 }}>
            <div className="big">总编</div>
            <div>我可以帮你调度 Worker、检查设定、或者就项目状态答疑。</div>
            <div className="muted tiny" style={{ marginTop: 8 }}>试试问：「现在写到第几章了？」</div>
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`chief-msg ${m.role}`}>
            <div className="ava">{m.role === "user" ? "你" : "总"}</div>
            <div>
              <div className="body">{m.content}</div>
              {m.thinking && <div className="thinking">思考：{m.thinking}</div>}
              {m.actions && m.actions.length > 0 && (
                <div className="actions">
                  {m.actions.map((a: any, i: number) => (
                    <div key={i} style={{ minWidth: 200, maxWidth: 320 }}>
                      <div className="tiny muted" style={{ marginBottom: 4 }}>{a.description ?? a.type}</div>
                      <button
                        className="primary"
                        onClick={() => onAction(a.action_id, a.type, a.params)}
                      >
                        {a.label ?? a.type}
                      </button>
                      {actionFeedback?.id === a.action_id && (
                        <div className={actionFeedback?.ok ? "ok tiny" : "error tiny"} style={{ marginTop: 4 }}>
                          {actionFeedback?.msg}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {(m.tokens_in || m.tokens_out || m.cost_usd) && (
                <div className="muted tiny mono" style={{ marginTop: 4 }}>
                  {m.tokens_in}/{m.tokens_out} tok · ${m.cost_usd.toFixed(4)}
                </div>
              )}
            </div>
          </div>
        ))}
        {streaming && (
          <div className="chief-msg chief">
            <div className="ava">总</div>
            <div className="body"><span className="spinner" /> 思考中…</div>
          </div>
        )}
      </div>

      <div className="chief-input">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
          placeholder={projectId ? "和总编聊项目… (Enter 发送)" : "需要先选择或新建一个项目"}
          disabled={!projectId || streaming}
        />
        <button className="primary" onClick={onSend} disabled={!input.trim() || streaming || !projectId}>
          发送
        </button>
      </div>
    </aside>
  );
}
