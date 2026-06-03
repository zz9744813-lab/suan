import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useProjectStore } from "../stores/projectStore";
import { useWorkerStore } from "../stores/workerStore";
import { useEventStore } from "../stores/eventStore";
import {
  listTasks, workerStart, workerPause, workerResume, workerStop,
  getDefaultPolicy, getTask, taskSteps, retryTask, cancelTask,
} from "../api";
import type { AgentTask, WorkerPolicy, AgentStep } from "../types";
import "./Dashboard.css";

/**
 * Round-1 dashboard:
 *   - P1-UI-6 (filter sse.heartbeat) is handled in eventStore; we
 *     additionally cap the feed to the most recent 20 events to
 *     keep the page calm.
 *   - P1-UI-7 (readable error display) lives in FailureDiagnosisCard
 *     below — the most recent failed task gets a dedicated card with
 *     copy / view step / retry / cancel actions.
 *   - P1-UI-5 (创作总控台) is the goal; this first pass adds the
 *     structured surface area. The full CurrentPipelinePanel +
 *     AgentStepRail + ChapterPreviewCard round-3 work extends this.
 */
export function Dashboard() {
  const projects = useProjectStore((s) => s.projects);
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const worker = useWorkerStore((s) => s.status);
  const refreshWorker = useWorkerStore((s) => s.refresh);
  const workerStartPolling = useWorkerStore((s) => s.startPolling);
  const events = useEventStore((s) => s.events);
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [policy, setPolicy] = useState<WorkerPolicy | null>(null);

  useEffect(() => {
    listTasks({ limit: 12 }).then(setTasks).catch(() => {});
    const id = window.setInterval(() => {
      listTasks({ limit: 12 }).then(setTasks).catch(() => {});
    }, 4000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (currentProjectId) {
      getDefaultPolicy().then(setPolicy).catch(() => {});
    }
  }, [currentProjectId]);

  const currentProject = projects.find((p) => p.id === currentProjectId);
  const totalChapters = projects.reduce((s, p) => s + p.chapter_count, 0);
  const totalWords = projects.reduce((s, p) => s + p.total_words, 0);
  const totalTargetWords = projects.reduce((s, p) => s + p.target_word_count, 0);
  const todayWords = worker?.today_words ?? 0;
  const todayCost = worker?.today_cost_usd ?? 0;
  const todayTarget = policy?.daily_word_goal ?? 30000;

  // P1-UI-7: most recent failed task in the top-12 list drives the
  // FailureDiagnosisCard. Picked lazily so the card doesn't render
  // anything when there are no failures.
  const latestFailed = useMemo(
    () => tasks.find((t) => t.status === "failed" || t.status === "cancelled") ?? null,
    [tasks]
  );

  return (
    <div className="dashboard">
      <header className="page-header">
        <div>
          <h1 className="page-title">工作台</h1>
          <p className="page-subtitle">
            {currentProject ? `当前项目：${currentProject.name}` : "还没有选择项目 — 左侧新建一个项目开始"}
          </p>
        </div>
        <div className="row">
          {worker?.state !== "running" && (
            <button className="primary" onClick={async () => { await workerStart(); refreshWorker(); }}>启动 Worker</button>
          )}
          {worker?.state === "running" && (
            <button onClick={async () => { await workerPause(); refreshWorker(); }}>暂停</button>
          )}
          {worker?.state === "paused" && (
            <button onClick={async () => { await workerResume(); refreshWorker(); }}>恢复</button>
          )}
          {worker && worker.state !== "stopped" && worker.state !== "idle" && (
            <button className="danger" onClick={async () => { await workerStop(); refreshWorker(); }}>停止</button>
          )}
        </div>
      </header>

      <div className="dashboard-grid">
        {/* === KPI row === */}
        <KpiCard
          title="今日字数"
          value={formatNumber(todayWords)}
          sub={`目标 ${formatNumber(todayTarget)} · ${Math.round((todayWords / Math.max(1, todayTarget)) * 100)}%`}
          progress={Math.min(100, (todayWords / Math.max(1, todayTarget)) * 100)}
        />
        <KpiCard
          title="今日成本"
          value={`$${todayCost.toFixed(3)}`}
          sub={`预算 $${policy?.daily_budget_usd.toFixed(2) ?? "—"}`}
          progress={Math.min(100, (todayCost / Math.max(0.01, policy?.daily_budget_usd ?? 8)) * 100)}
          progressClass={todayCost > (policy?.daily_budget_usd ?? 8) * 0.8 ? "warn" : "ok"}
        />
        <KpiCard
          title="总字数 / 总目标"
          value={`${formatNumber(totalWords)} / ${formatNumber(totalTargetWords)}`}
          sub={`${projects.length} 个项目 · ${totalChapters} 章`}
          progress={Math.min(100, (totalWords / Math.max(1, totalTargetWords)) * 100)}
        />
        <KpiCard
          title="连续失败"
          value={String(worker?.consecutive_failures ?? 0)}
          sub={worker?.last_error ? `最近：${worker.last_error.slice(0, 30)}…` : "无"}
          progressClass={(worker?.consecutive_failures ?? 0) > 0 ? "warn" : "ok"}
        />

        {/* === P1-UI-7: Failure diagnosis (only when there's something to show) === */}
        {latestFailed && (
          <section className="card span-2">
            <FailureDiagnosisCard task={latestFailed} onChanged={() => listTasks({ limit: 12 }).then(setTasks).catch(() => {})} />
          </section>
        )}

        {/* === Recent tasks === */}
        <section className="card span-2">
          <div className="card-header">
            <h3>最近任务</h3>
            <Link to="/tasks" className="muted small">查看全部 →</Link>
          </div>
          {tasks.length === 0 ? (
            <div className="empty">还没有任务。新建一个项目后可以排章节流水线。</div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: 40 }}>#</th>
                  <th>类型</th>
                  <th>章节</th>
                  <th>状态</th>
                  <th style={{ textAlign: "right" }}>成本</th>
                  <th style={{ textAlign: "right" }}>Tokens</th>
                  <th>时间</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((t) => (
                  <tr key={t.id}>
                    <td className="mono muted">{t.id}</td>
                    <td>{t.task_type}</td>
                    <td>
                      {t.chapter_id ? (
                        <Link to={`/projects/${t.project_id}/chapters/${t.chapter_id}`}>
                          第 {t.chapter_id} 章
                        </Link>
                      ) : <span className="muted">—</span>}
                    </td>
                    <td>
                      <span className={`badge ${statusClass(t.status)}`}>{t.status}</span>
                    </td>
                    <td className="mono" style={{ textAlign: "right" }}>${t.cost_usd.toFixed(4)}</td>
                    <td className="mono muted" style={{ textAlign: "right" }}>
                      {(t.input_tokens / 1000).toFixed(1)}k / {(t.output_tokens / 1000).toFixed(1)}k
                    </td>
                    <td className="muted small">{formatTime(t.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {/* === Event timeline === */}
        <section className="card">
          <div className="card-header">
            <h3>实时事件</h3>
            <span className="muted small">最近 {Math.min(20, events.length)} 条</span>
          </div>
          <div className="event-feed">
            {events.length === 0 ? (
              <div className="empty">等待事件…</div>
            ) : (
              [...events].reverse().slice(0, 20).map((e) => (
                <div key={e.id} className={`event-row event-${e.level}`}>
                  <span className="event-time mono tiny">{formatTime(new Date(e.ts * 1000).toISOString())}</span>
                  <span className={`badge event-type event-type-${e.level}`}>{e.event_type}</span>
                  <span className="event-msg ellipsis">{e.message}</span>
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function KpiCard({
  title, value, sub, progress, progressClass,
}: { title: string; value: string; sub: string; progress?: number; progressClass?: "ok" | "warn" }) {
  return (
    <div className="kpi-card">
      <div className="kpi-title">{title}</div>
      <div className="kpi-value serif">{value}</div>
      <div className="kpi-sub muted small">{sub}</div>
      {progress !== undefined && (
        <div className="kpi-bar">
          <div
            className={`kpi-bar-fill ${progressClass ?? "gold"}`}
            style={{ width: `${progress}%` }}
          />
        </div>
      )}
    </div>
  );
}

/**
 * P1-UI-7: takes a failed / cancelled task and renders an
 * actionable failure card. Loads the task's full record + steps
 * lazily so the dashboard stays cheap on the happy path.
 *
 * Action surface:
 *   - 复制错误  : copies the original error string to clipboard
 *   - 查看 Step  : jumps to the chapter detail page (which already
 *                 renders the step timeline)
 *   - 从头重试   : calls /api/tasks/{id}/retry (status flip to pending)
 *   - 取消任务   : calls /api/tasks/{id}/cancel
 *   - 打开诊断   : link to /projects/{pid}/chapters/{cid}
 */
function FailureDiagnosisCard({ task, onChanged }: { task: AgentTask; onChanged: () => void }) {
  const [details, setDetails] = useState<{ task: AgentTask; steps: AgentStep[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [t, steps] = await Promise.all([getTask(task.id), taskSteps(task.id)]);
        if (!cancelled) setDetails({ task: t, steps: steps });
      } catch {
        /* ignore — card still renders with the summary */
      }
    })();
    return () => { cancelled = true; };
  }, [task.id]);

  const failedStep = details?.steps.find((s) => s.status === "failed");
  const errorText = details?.task.error ?? task.error ?? "（未提供错误信息）";
  const errorType = classifyError(errorText);
  const suggestion = suggestionFor(errorType);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(errorText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard may be blocked; fail quietly */
    }
  };

  const onRetry = async () => {
    setBusy(true);
    try { await retryTask(task.id); onChanged(); } finally { setBusy(false); }
  };
  const onCancel = async () => {
    setBusy(true);
    try { await cancelTask(task.id); onChanged(); } finally { setBusy(false); }
  };

  return (
    <div className="failure-card">
      <div className="card-header">
        <h3>
          <span className="badge error">失败</span>
          任务 #{task.id} · {task.task_type}
        </h3>
        <span className="muted small">{formatTime(details?.task.created_at ?? task.created_at)}</span>
      </div>

      <div className="failure-grid">
        <div className="failure-cell">
          <div className="k tiny muted">错误类型</div>
          <div className="v"><b className="warn">{errorType}</b></div>
        </div>
        <div className="failure-cell">
          <div className="k tiny muted">失败 Agent</div>
          <div className="v">{failedStep?.agent_name ?? <span className="muted">未识别</span>}</div>
        </div>
        <div className="failure-cell">
          <div className="k tiny muted">失败 Step</div>
          <div className="v">{failedStep?.step_name ?? <span className="muted">未识别</span>}</div>
        </div>
        <div className="failure-cell">
          <div className="k tiny muted">章节</div>
          <div className="v">
            {task.chapter_id ? (
              <Link to={`/projects/${task.project_id}/chapters/${task.chapter_id}`}>
                第 {task.chapter_id} 章
              </Link>
            ) : <span className="muted">—</span>}
          </div>
        </div>
      </div>

      <div className="failure-section">
        <div className="k tiny muted">错误摘要</div>
        <details open>
          <summary className="failure-summary">点击展开 / 收起</summary>
          <pre className="failure-pre">{errorText}</pre>
        </details>
      </div>

      {failedStep?.raw_output && (
        <div className="failure-section">
          <div className="k tiny muted">原始输出 preview（前 800 字）</div>
          <pre className="failure-pre faint">{(failedStep.raw_output ?? "").slice(0, 800)}</pre>
        </div>
      )}

      {suggestion && (
        <div className="failure-section">
          <div className="k tiny muted">建议操作</div>
          <div className="failure-suggestion">{suggestion}</div>
        </div>
      )}

      <div className="failure-actions">
        <button onClick={onCopy} disabled={busy}>
          {copied ? "已复制 ✓" : "复制错误"}
        </button>
        {task.chapter_id && (
          <Link to={`/projects/${task.project_id}/chapters/${task.chapter_id}`} className="button">
            查看 Step
          </Link>
        )}
        <button onClick={onRetry} disabled={busy || task.status === "running"}>重试</button>
        {task.status === "running" && (
          <button className="danger" onClick={onCancel} disabled={busy}>取消任务</button>
        )}
        <span className="spacer" />
        <Link to="/models" className="button">打开模型配置</Link>
      </div>
    </div>
  );
}

function classifyError(text: string): string {
  const t = (text || "").toLowerCase();
  if (t.includes("non-json") || t.includes("json") || t.includes("jsondecode") || t.includes("json_object")) return "JSON 解析失败";
  if (t.includes("401") || t.includes("unauthorized") || t.includes("auth")) return "鉴权失败";
  if (t.includes("404")) return "模型 / URL 不存在";
  if (t.includes("timeout") || t.includes("超时")) return "请求超时";
  if (t.includes("connection") || t.includes("无法连接")) return "无法连接模型";
  if (t.includes("cancel")) return "用户取消";
  if (t.includes("rate") || t.includes("limit") || t.includes("429")) return "频率限制";
  if (t.includes("budget") || t.includes("预算")) return "预算耗尽";
  return "未分类错误";
}

function suggestionFor(type: string): string | null {
  switch (type) {
    case "JSON 解析失败":
      return "Critic/Drafter 输出的不是合法 JSON。建议在 Prompt 强调“只返回 JSON”，或在「模型配置」中检查温度/模型能力。";
    case "鉴权失败":
      return "API Key 无效或过期。打开「模型配置」检查对应 Provider 的 Key 是否被替换或撤销。";
    case "模型 / URL 不存在":
      return "Provider 的 Base URL 或模型名拼写错误，或该模型已下线。请在「模型配置」页面测试连接。";
    case "请求超时":
      return "模型响应过慢。可尝试：1) 切换到更小的模型；2) 减少 max_tokens；3) 检查网络代理。";
    case "无法连接模型":
      return "Base URL 不可访问或网络受限。检查代理 / 防火墙设置，必要时换一个 Provider。";
    case "频率限制":
      return "Provider 触发了限流。稍等片刻再重试，或在「Worker」页面临时调低任务频率。";
    case "预算耗尽":
      return "今日成本已超过日预算。调高 daily_budget_usd 或等第二天再继续。";
    case "用户取消":
      return null;
    default:
      return "请复制错误后查看「任务 → Step」详情，或让总编帮忙诊断。";
  }
}

function statusClass(s: string): "ok" | "warn" | "error" | "info" {
  if (s === "succeeded") return "ok";
  if (s === "running" || s === "pending") return "info";
  if (s === "failed" || s === "cancelled") return "error";
  return "warn";
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return iso;
  }
}

function formatNumber(n: number): string {
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`;
  return n.toLocaleString();
}
