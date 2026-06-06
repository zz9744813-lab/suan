/**
 * TasksPage — 任务中心 (P0 重构)
 *
 * 从表格日志改成任务看板:
 *   - 顶部统计: 运行中/等待/失败/今日完成/今日成本
 *   - 分类 Tab: 全部/写作/拆书/模型/讨论/记忆/导出/失败
 *   - 任务卡片: 进度条+产物摘要+阶段轨道
 *   - 点击卡片展开详情: 阶段步骤+内部事件(默认折叠)
 *   - 内部子任务 (study_character等) 不出现,只在详情事件里折叠显示
 */
import { useEffect, useState, useCallback, useMemo } from "react";
import {
  listTasks, retryTask, cancelTask, taskSteps,
} from "../api";
import type { AgentTask, AgentStep } from "../types";
import { CommandCenterPanel } from "../components/tasks/CommandCenterPanel";
import "./TasksPage.css";

type DomainTab = "all" | "writing" | "model" | "discussion" | "memory" | "export" | "failed";

const DOMAINS: { key: DomainTab; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "writing", label: "写作" },
  { key: "model", label: "模型" },
  { key: "discussion", label: "讨论" },
  { key: "memory", label: "记忆" },
  { key: "export", label: "导出" },
  { key: "failed", label: "失败" },
];

const STAGE_LABELS: Record<string, string> = {
  chapterize: "分章", chapter_profile: "章节画像", entity_extract: "实体抽取",
  event_extract: "事件抽取", scene_beat_extract: "场景节拍", relationship_analyze: "关系分析",
  foreshadow_analyze: "伏笔分析", behavior_pattern_mine: "行为模式", technique_mine: "写作技巧",
  graph_finalize: "图谱整理", study_critic: "质量审查", knowledge_index: "知识索引",
  writing_context_sync: "同步写作",
  planner:"规划", draft:"写作", critic:"评审", reader_feedback:"读者反馈",
  discussion:"讨论", rewrite:"返工", continuity:"连续", learning:"学习", memory_update:"记忆更新",
};

// P0 修复: 硬过滤历史脏任务, 即便后端 visibility 不规范也不会刷屏
const HIDDEN_TASK_KINDS = new Set([
  "comment_cleanup", "heartbeat", "cleanup", "audit_cleanup",
  "study_character", "study_event", "study_relationship", "study_behavior",
  "study_bulk_character", "study_bulk_event", "study_bulk_relationship",
  "study_bulk_behavior", "study_bulk_foreshadow", "study_bulk_technique",
  "study_technique", "study_foreshadow", "study_behavior_pattern",
  "deepstudy_stage", "deepstudy_run_internal",
]);
const HIDDEN_TASK_TYPES = new Set([
  "comment_cleanup", "study_character", "study_event",
  "study_relationship", "study_behavior", "study_bulk_*",
  "heartbeat", "cleanup", "audit_cleanup",
]);

function isDeepStudyTask(task: AgentTask) {
  const domain = task.domain || "";
  const kind = (task.task_kind || task.task_type || "").toLowerCase();
  // 后端 domain 已经是 deepstudy
  if (domain === "deepstudy") return true;
  if (HIDDEN_TASK_KINDS.has(task.task_kind || "")) return true;
  if (HIDDEN_TASK_TYPES.has(task.task_type || "")) return true;
  // 兜底: kind 前缀命中
  return kind.startsWith("deepstudy")
    || kind.startsWith("study_")
    || kind === "study"
    || kind === "study_bulk"
    || kind === "chapterize"
    || kind === "study_material";
}

export function TasksPage() {
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [domain, setDomain] = useState<DomainTab>("all");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [stepsLoading, setStepsLoading] = useState(false);
  const [busyTaskId, setBusyTaskId] = useState<number | null>(null);
  const [flash, setFlash] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  // Internal events toggle
  const [showInternalEvents, setShowInternalEvents] = useState(false);

  const reload = useCallback(() => {
    const params: any = { limit: 100, visibility: "user" };
    if (domain === "failed") {
      params.status = "failed";
    } else if (domain !== "all") {
      params.domain = domain;
    }
    listTasks(params).then(setTasks).catch(() => {});
  }, [domain]);

  useEffect(() => {
    reload();
    const t = window.setInterval(reload, 5000);
    return () => window.clearInterval(t);
  }, [reload]);

  useEffect(() => {
    if (expandedId == null) { setSteps([]); setShowInternalEvents(false); return; }
    setStepsLoading(true);
    taskSteps(expandedId)
      .then((s) => setSteps(s))
      .catch(() => setSteps([]))
      .finally(() => setStepsLoading(false));
  }, [expandedId]);

  async function doRetry(t: AgentTask) {
    if (!confirm(`重试任务 "${t.display_title || t.task_type}"?`)) return;
    setBusyTaskId(t.id); setFlash(null);
    try {
      await retryTask(t.id, { mode: "full" });
      setFlash({ type: "ok", text: `任务已重新入队` });
      reload();
    } catch (e: any) {
      setFlash({ type: "err", text: `重试失败: ${e.message}` });
    } finally {
      setBusyTaskId(null);
      setTimeout(() => setFlash(null), 3000);
    }
  }

  async function doCancel(t: AgentTask) {
    if (!confirm(`取消任务 "${t.display_title || t.task_type}"?`)) return;
    setBusyTaskId(t.id); setFlash(null);
    try {
      await cancelTask(t.id);
      setFlash({ type: "ok", text: `任务已取消` });
      reload();
    } catch (e: any) {
      setFlash({ type: "err", text: `取消失败: ${e.message}` });
    } finally {
      setBusyTaskId(null);
      setTimeout(() => setFlash(null), 3000);
    }
  }

  const visibleTasks = useMemo(() => tasks.filter((t) => !isDeepStudyTask(t)), [tasks]);

  const stats = useMemo(() => ({
    running: visibleTasks.filter((t) => t.status === "running").length,
    pending: visibleTasks.filter((t) => t.status === "pending" || t.status === "queued").length,
    failed: visibleTasks.filter((t) => t.status === "failed").length,
    succeeded: visibleTasks.filter((t) => t.status === "succeeded").length,
    cost: visibleTasks.reduce((s, t) => s + (t.cost_usd || 0), 0),
    tokens: visibleTasks.reduce((s, t) => s + (t.input_tokens || 0) + (t.output_tokens || 0), 0),
  }), [visibleTasks]);

  // Internal steps: filter out user-level
  const userSteps = useMemo(() => steps.filter((s) => s.step_name !== "study_character" && s.step_name !== "study_event"), [steps]);
  const internalSteps = useMemo(() => steps.filter((s) => s.step_name === "study_character" || s.step_name === "study_event"), [steps]);

  return (
    <div className="main-body tasks-page">
      {/* Top stats bar */}
      <div className="tasks-stats-bar">
        <span className="tasks-stat">
          <span className="tasks-stat-num" style={{ color: "var(--accent)" }}>{stats.running}</span>
          <span className="tasks-stat-label">运行中</span>
        </span>
        <span className="tasks-stat">
          <span className="tasks-stat-num">{stats.pending}</span>
          <span className="tasks-stat-label">等待</span>
        </span>
        <span className="tasks-stat">
          <span className="tasks-stat-num" style={{ color: stats.failed > 0 ? "var(--danger)" : undefined }}>{stats.failed}</span>
          <span className="tasks-stat-label">失败</span>
        </span>
        <span className="tasks-stat">
          <span className="tasks-stat-num">{stats.succeeded}</span>
          <span className="tasks-stat-label">已完成</span>
        </span>
        <span className="tasks-stat">
          <span className="tasks-stat-num">${stats.cost.toFixed(3)}</span>
          <span className="tasks-stat-label">成本</span>
        </span>
        <span className="tasks-stat">
          <span className="tasks-stat-num">{(stats.tokens / 1000).toFixed(1)}k</span>
          <span className="tasks-stat-label">Token</span>
        </span>
      </div>

      {/* Domain tabs */}
      <div className="tasks-filter-row">
        {DOMAINS.map((d) => (
          <button
            key={d.key}
            className={`tasks-filter-chip ${domain === d.key ? "active" : ""}`}
            onClick={() => setDomain(d.key)}
          >
            {d.label}
          </button>
        ))}
      </div>

      {flash && (
        <div className={`tasks-flash tasks-flash-${flash.type}`}>{flash.text}</div>
      )}

      {/* P0 任务中控台 — 顶部固定, 8s 轮询 */}
      <CommandCenterPanel
        pollIntervalMs={8000}
        onTaskClick={(id) => {
          // 点中控台任务 → 选中该任务并展开详情
          setExpandedId(id);
          // 滚动到该任务卡
          setTimeout(() => {
            const el = document.getElementById(`task-card-${id}`);
            if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
          }, 100);
        }}
      />

      {/* Task card list */}
      <div className="tasks-card-list">
        {visibleTasks.length === 0 ? (
          <div className="card" style={{ padding: 24, textAlign: "center" }}>
            <div className="muted">暂无任务</div>
          </div>
        ) : (
          visibleTasks.map((t) => {
            const expanded = expandedId === t.id;
            const progressPct = (t.progress_total ?? 0) > 0
              ? Math.min(100, Math.round(((t.progress_current ?? 0) / (t.progress_total ?? 1)) * 100))
              : 0;
            const title = t.display_title || `${t.task_type} #${t.id}`;
            const statusCls = t.status === "running" ? "running" : t.status === "failed" ? "error" : t.status === "succeeded" ? "ok" : "";
            const stageLabel = t.stage_key ? (STAGE_LABELS[t.stage_key] || t.stage_key) : "";
            const summary = (t as any).summary_json || {};

            return (
              <div key={t.id} id={`task-card-${t.id}`} className={`card task-card ${expanded ? "expanded" : ""}`}>
                {/* Card header */}
                <div className="task-card-head" onClick={() => setExpandedId(expanded ? null : t.id)} style={{ cursor: "pointer" }}>
                  <div className="task-card-title-row">
                    <span className="task-card-caret">{expanded ? "▼" : "▶"}</span>
                    <b className="task-card-title">{title}</b>
                    <span className={`pill tiny ${statusCls}`}>{t.status}</span>
                    {t.domain && <span className="pill tiny muted">{t.domain}</span>}
                    {stageLabel && <span className="muted tiny">{stageLabel}</span>}
                    <span className="spacer" />
                    {t.cost_usd > 0 && <span className="muted tiny">${t.cost_usd.toFixed(4)}</span>}
                    {t.progress_total != null && t.progress_total > 0 && (
                      <span className="muted tiny">{t.progress_current ?? 0}/{t.progress_total}</span>
                    )}
                  </div>
                  {/* Progress bar */}
                  {progressPct > 0 && (
                    <div className="task-card-progress">
                      <div className="task-card-progress-fill" style={{ width: `${progressPct}%` }} />
                    </div>
                  )}
                  {/* Summary badges */}
                  {summary && Object.keys(summary).length > 0 && (
                    <div className="task-card-summary">
                      {summary.characters > 0 && <span>人物 {summary.characters}</span>}
                      {summary.events > 0 && <span>事件 {summary.events}</span>}
                      {summary.behaviors > 0 && <span>行为 {summary.behaviors}</span>}
                      {summary.techniques > 0 && <span>技巧 {summary.techniques}</span>}
                      {summary.graph_nodes > 0 && <span>图谱 {summary.graph_nodes}</span>}
                    </div>
                  )}
                </div>

                {/* Expanded detail */}
                {expanded && (
                  <div className="task-card-detail">
                    {/* Error */}
                    {t.error && (
                      <div className="tasks-detail-block">
                        <div className="detail-title">错误</div>
                        <pre className="error-text">{t.error}</pre>
                      </div>
                    )}

                    {/* Stage rail */}
                {t.stage_key && (
                  <div className="task-card-stage">
                    <span className="muted tiny">当前阶段: {stageLabel}</span>
                    {t.progress_total && t.progress_total > 0 && (
                      <span className="task-card-stage-bar" style={{ marginLeft: 8 }}>
                        {Array.from({ length: Math.min(14, t.progress_total) }).map((_, i) => {
                              const done = i < (t.progress_current ?? 0);
                              return (
                                <span
                                  key={i}
                                  className={`task-stage-dot ${done ? "done" : ""}`}
                                  title={done ? "已完成" : "等待"}
                                />
                              );
                            })}
                          </span>
                        )}
                      </div>
                    )}

                    {/* User-level steps */}
                    <div className="tasks-detail-block">
                      <div className="detail-title">
                        步骤 ({userSteps.length})
                      </div>
                      {stepsLoading ? (
                        <div className="muted small">加载中…</div>
                      ) : userSteps.length === 0 ? (
                        <div className="muted small">无步骤记录</div>
                      ) : (
                        <table className="steps-table">
                          <thead>
                            <tr>
                              <th>步骤</th><th>Agent</th><th>状态</th>
                              <th>模型</th>
                              <th style={{ textAlign: "right" }}>耗时</th>
                              <th style={{ textAlign: "right" }}>成本</th>
                            </tr>
                          </thead>
                          <tbody>
                            {userSteps.map((s) => (
                              <tr key={s.id}>
                                <td className="mono small">{s.step_name}</td>
                                <td className="muted small">{s.agent_name}</td>
                                <td><span className={`pill tiny ${s.status}`}>{s.status}</span></td>
                                <td className="muted tiny">{s.model_name ?? "—"}</td>
                                <td className="mono tiny" style={{ textAlign: "right" }}>{s.duration_ms}ms</td>
                                <td className="mono tiny" style={{ textAlign: "right" }}>${s.cost_usd.toFixed(4)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </div>

                    {/* Internal events (collapsed by default) */}
                    {internalSteps.length > 0 && (
                      <div className="tasks-detail-block">
                        <button
                          className="link small"
                          onClick={() => setShowInternalEvents(!showInternalEvents)}
                        >
                          {showInternalEvents ? "收起" : "展开"} 内部事件 ({internalSteps.length})
                        </button>
                        {showInternalEvents && (
                          <div style={{ marginTop: 8, maxHeight: 300, overflowY: "auto" }}>
                            {internalSteps.map((s) => (
                              <div key={s.id} className="muted tiny" style={{ padding: "2px 0", borderBottom: "1px solid var(--border)" }}>
                                <span className={`pill tiny ${s.status}`}>{s.status}</span>
                                {" "}{s.step_name} · {s.agent_name}
                                {s.duration_ms ? ` · ${s.duration_ms}ms` : ""}
                                {s.cost_usd ? ` · $${s.cost_usd.toFixed(4)}` : ""}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Actions */}
                    <div className="task-card-actions">
                      <span className="muted tiny">
                        {t.started_at ? new Date(t.started_at).toLocaleString() : "—"}
                        {" → "}
                        {t.finished_at ? new Date(t.finished_at).toLocaleString() : "运行中"}
                      </span>
                      <span className="spacer" />
                      {t.status === "failed" && (
                        <button
                          className="primary small"
                          onClick={() => doRetry(t)}
                          disabled={busyTaskId === t.id}
                        >
                          {busyTaskId === t.id ? "..." : "重试"}
                        </button>
                      )}
                      {(t.status === "pending" || t.status === "running" || t.status === "queued") && (
                        <button
                          className="link small"
                          onClick={() => doCancel(t)}
                          disabled={busyTaskId === t.id}
                        >
                          {busyTaskId === t.id ? "..." : "取消"}
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
