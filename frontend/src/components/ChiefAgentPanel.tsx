import { useEffect, useRef, useState } from "react";
import { useChiefStore } from "../stores/chiefStore";
import {
  confirmChiefAction,
  createChiefSession,
  listChiefSessions,
} from "../api";
import type { PanelMode } from "../stores/layoutStore";

type Props = {
  projectId: number | null;
  mode: PanelMode;
  onCycle: () => void;
};

// 右侧总编调度面板（spec §5.4 / §17.1）
// 形态：会话列表 + 当前消息流 + 输入框 + 操作卡片
// P0-UI-4: 支持 expanded / compact 两种渲染模式。
// hidden 模式下 AppShell 不会渲染本组件。
export function ChiefAgentPanel({ projectId, mode, onCycle }: Props) {
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
    if (mode === "expanded" && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streaming, mode]);

  useEffect(() => {
    if (mode === "expanded") {
      listChiefSessions(projectId ?? undefined).then(setSessionList).catch(() => {});
    }
  }, [projectId, session, mode]);

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

  // Compact mode: just an avatar + status dot + expand button.
  if (mode === "compact") {
    return (
      <aside className="chief-panel chief-compact">
        <button
          className="chief-compact-expand"
          onClick={onCycle}
          title="展开总编面板"
          aria-label="展开总编面板"
        >
          <div className="chief-avatar small">总</div>
          <div className="chief-compact-stack">
            <div className="chief-compact-label">总编</div>
            <div className={`chief-compact-dot chief-compact-dot-${streaming ? "warn" : session ? "ok" : "info"}`} />
          </div>
        </button>
      </aside>
    );
  }

  // Quick-command shortcuts — surfaced when there's no active
  // conversation so the panel isn't a blank box. Each item routes
  // through the normal send() path so the same LLM-driven actions
  // pipeline runs (P0-UI-4 验收标准 3, 4).
  const QUICK_COMMANDS = [
    { label: "诊断最近失败", message: "诊断最近一次失败的 Task，并告诉我应该先修什么。" },
    { label: "继续写下一章", message: "Worker 暂停时，帮我在当前项目里创建下一章任务并继续。" },
    { label: "检查模型配置", message: "检查当前所有模型 Provider 的健康度，并指出 Critic 风险。" },
    { label: "生成后续 10 章大纲", message: "基于当前项目已有大纲和最近章节走向，再生成 10 章后续大纲。" },
    { label: "总结当前项目状态", message: "总结当前项目的状态、字数、章节进度和 Worker 状态。" },
    { label: "查询拆书行为模式", message: "在拆书行为模式里，查找「热血主角 + 亲友受辱」的典型行为。" },
  ];

  const onQuick = (message: string) => {
    setInput(message);
    // submit on the next tick so the input state is reflected
    setTimeout(() => {
      onSend();
    }, 0);
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
        <button
          className="chief-cycle-btn"
          onClick={onCycle}
          title="折叠为窄栏"
          aria-label="折叠总编面板"
        >
          ▶
        </button>
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
          <div className="chief-quickstart">
            <div className="chief-quickstart-head">
              <div className="big">总编</div>
              <div className="muted small">没有会话时，可以直接选一个常用动作：</div>
            </div>
            <div className="chief-quickstart-grid">
              {QUICK_COMMANDS.map((q) => (
                <button
                  key={q.label}
                  className="chief-quickstart-item"
                  onClick={() => onQuick(q.message)}
                  title={q.message}
                >
                  {q.label}
                </button>
              ))}
            </div>
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
