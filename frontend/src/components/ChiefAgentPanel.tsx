import { useEffect, useRef, useState } from "react";
import { useChiefStore } from "../stores/chiefStore";
import { useLayoutStore } from "../stores/layoutStore";
import {
  confirmChiefAction,
  createChiefSession,
  listChiefSessions,
} from "../api";
import type { PanelMode } from "../stores/layoutStore";

type Props = {
  projectId: number | null;
  mode: PanelMode;
  // R15 / P0-CHIEF-1: the route we're on, so the panel can swap
  // quick-command suggestions to match what the user is doing.
  pageContext?: string;
  onCycle: () => void;
  // R12.2 / P0-UI-7b: separate "minimize to compact" from "hide
  // entirely". The compact button now ALWAYS expands — clicking the
  // visible "总" avatar should never make the panel disappear.
  // ``onHide`` is the new path that takes the user to fully hidden,
  // and ``onRestore`` is exposed so the BottomStatusBar can offer a
  // recovery affordance when the user is stuck in hidden.
  onHide?: () => void;
};

// Quick-command presets keyed by page route prefix. When the user is
// on /models, the ChiefAgentPanel should suggest "检查所有 Provider"
// not "继续写下一章". We pick the FIRST prefix that matches, falling
// back to "default" for any unrecognised route. R15 / P0-CHIEF-1.
const QUICK_COMMANDS_BY_PAGE: Array<{ match: RegExp; items: Array<{ label: string; message: string }> }> = [
  {
    match: /^\/dashboard/,
    items: [
      { label: "诊断最近失败", message: "诊断最近一次失败的 Task，并告诉我应该先修什么。" },
      { label: "继续写下一章", message: "Worker 暂停时，帮我在当前项目里创建下一章任务并继续。" },
      { label: "检查模型配置", message: "检查当前所有模型 Provider 的健康度，并指出 Critic 风险。" },
      { label: "生成后续 10 章大纲", message: "基于当前项目已有大纲和最近章节走向，再生成 10 章后续大纲。" },
      { label: "总结当前项目状态", message: "总结当前项目的状态、字数、章节进度和 Worker 状态。" },
    ],
  },
  {
    match: /^\/projects/,
    items: [
      { label: "总结当前项目", message: "总结当前打开的项目的进度、最近章节和关键问题。" },
      { label: "继续写下一章", message: "为当前项目创建下一章任务并让 Worker 开始写。" },
      { label: "查看最近失败", message: "查看当前项目最近一次失败的 Task 并给出修复建议。" },
      { label: "查询拆书行为模式", message: "在拆书行为模式里，查找与当前项目主角匹配的行为模式。" },
    ],
  },
  {
    match: /^\/models/,
    items: [
      { label: "检查所有 Provider", message: "对当前所有模型 Provider 跑一次完整健康检查（short_chat / json / critic），告诉我哪些能用于 Critic。" },
      { label: "测试 Critic JSON", message: "用一个 Critic schema 测试 Prompt 跑一遍，确认返回 JSON 完整。" },
      { label: "推荐角色绑定", message: "基于 Provider 速度 / JSON 稳定性 / 上下文长度，给出 Planner/Drafter/Critic/Rewriter 的推荐角色绑定。" },
      { label: "标记风险模型", message: "把所有不能稳定输出 Critic JSON 的模型标记为 Critic 不可用。" },
    ],
  },
  {
    match: /^\/study/,
    items: [
      { label: "开始拆书", message: "对当前选中的拆书材料开始 Agent 化分析（人物 / 事件 / 行为模式 / 图谱）。" },
      { label: "生成行为模式", message: "从已抽取的人物 / 事件里聚类出 5 条最值得复用的行为模式。" },
      { label: "查询人物卡", message: "在当前项目的拆书库里，查找主角和女主的所有人物卡并总结。" },
      { label: "导出拆书结果", message: "把当前拆书材料的人物 / 事件 / 行为模式导出为 JSON 文件。" },
    ],
  },
  {
    match: /^\/behavior/,
    items: [
      { label: "查询行为模式", message: "在行为模式库里，查找「热血主角 + 公开羞辱」相关的 3 条典型行为。" },
      { label: "注入 Planner", message: "把当前匹配到的行为模式注入到下一章 Planner 的 prompt 中。" },
      { label: "聚类新模式", message: "基于最近 10 章的草稿和重写稿，提取 3 条新行为模式。" },
    ],
  },
  {
    match: /^\/graph/,
    items: [
      { label: "生成图谱", message: "基于当前项目的拆书结果和章节事件，重新生成人物 / 事件 / 关系图谱。" },
      { label: "查询人物关系", message: "列出主角在图谱中前 5 条最强的关系（敌 / 友 / 师 / 恋）。" },
      { label: "导出图谱 JSON", message: "把当前图谱导出为 JSON 用于第三方可视化工具。" },
    ],
  },
  {
    match: /^\/tasks/,
    items: [
      { label: "查看失败任务", message: "列出最近 5 个失败的 Task，对每个给出 1 句修复建议。" },
      { label: "重试全部失败", message: "把当前所有 failed 状态的 Task 全部重新入队（用 fallback 模式）。" },
      { label: "取消所有运行中", message: "把当前所有 running 状态的 Task 全部取消。" },
    ],
  },
  {
    match: /^\/worker/,
    items: [
      { label: "继续下一章", message: "Worker 暂停时，让它在当前项目里继续写下一章。" },
      { label: "切换策略预设", message: "把当前 Worker 策略切换为「稳妥优先」预设。" },
      { label: "查看 Worker 状态", message: "总结 Worker 当前状态、最近一次任务和今日字数 / 成本。" },
    ],
  },
  {
    match: /^\/prompts/,
    items: [
      { label: "检查活跃版本", message: "列出每个 Prompt 模板当前的活跃版本号和最近修改时间。" },
      { label: "对比 critic 模板", message: "把 critic 模板的当前激活版本和最近一个 deprecated 版本做 diff，告诉我变更点。" },
      { label: "起草新版本", message: "帮我在 critic_main 模板里起草一个新版本，要求更严格地输出 JSON。" },
    ],
  },
  {
    match: /^\/memory/,
    items: [
      { label: "列出活跃伏笔", message: "列出当前项目里 status=active 的所有伏笔。" },
      { label: "标记伏笔已回收", message: "把「玉佩」这个伏笔在当前项目里标记为 paid_off。" },
      { label: "添加新人物", message: "帮我在当前项目里加一个叫「沈落」的新人物卡（主角 / 热血 / 倔强）。" },
    ],
  },
  {
    match: /^\/discussion/,
    items: [
      { label: "开一场圆桌", message: "用 3 个角色开一场关于「下一章主线走向」的圆桌讨论。" },
      { label: "总结上次讨论", message: "总结当前项目最近一次圆桌讨论的结论。" },
    ],
  },
];

const DEFAULT_QUICK_COMMANDS: Array<{ label: string; message: string }> = [
  { label: "诊断最近失败", message: "诊断最近一次失败的 Task，并告诉我应该先修什么。" },
  { label: "检查模型配置", message: "检查当前所有模型 Provider 的健康度，并指出 Critic 风险。" },
  { label: "总结当前项目", message: "总结当前项目的状态、字数、章节进度和 Worker 状态。" },
  { label: "查询拆书行为模式", message: "在拆书行为模式里，查找「热血主角 + 亲友受辱」的典型行为。" },
];

function pickQuickCommands(pageContext?: string) {
  if (!pageContext) return DEFAULT_QUICK_COMMANDS;
  for (const group of QUICK_COMMANDS_BY_PAGE) {
    if (group.match.test(pageContext)) return group.items;
  }
  return DEFAULT_QUICK_COMMANDS;
}

// 右侧总编调度面板（spec §5.4 / §17.1）
// 形态：会话列表 + 当前消息流 + 输入框 + 操作卡片
// P0-UI-4: 支持 expanded / compact 两种渲染模式。
// hidden 模式下 AppShell 不会渲染本组件。
export function ChiefAgentPanel({ projectId, mode, pageContext, onCycle, onHide }: Props) {
  const session = useChiefStore((s) => s.session);
  const messages = useChiefStore((s) => s.messages);
  const streaming = useChiefStore((s) => s.streaming);
  const startSession = useChiefStore((s) => s.startSession);
  const send = useChiefStore((s) => s.send);
  const setChiefPanelMode = useLayoutStore((s) => s.setChiefPanelMode);
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
  // R12.2 fix: clicking the avatar ALWAYS expands to full panel
  // (not the cycle, which used to skip straight to "hidden" and
  // make the panel disappear with no obvious way back).
  if (mode === "compact") {
    return (
      <aside className="chief-panel chief-compact">
        <button
          className="chief-compact-expand"
          onClick={() => setChiefPanelMode("expanded")}
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
  // pipeline runs (P0-UI-4 验收标准 3, 4). R15 / P0-CHIEF-1: the
  // preset list now changes based on the current page route so the
  // suggestions match the user's current intent.
  const QUICK_COMMANDS = pickQuickCommands(pageContext);

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
          title="折叠为窄栏 (总编会缩成右侧 64px 小条)"
          aria-label="折叠总编面板"
        >
          ▶
        </button>
        {onHide && (
          <button
            className="chief-hide-btn"
            onClick={onHide}
            title="完全隐藏 (底部状态栏会留一个「恢复总编」按钮)"
            aria-label="完全隐藏总编面板"
          >
            ✕
          </button>
        )}
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
