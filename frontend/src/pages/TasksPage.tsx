/**
 * TasksPage — Mission Control Dashboard
 *
 * 3 区仪表盘布局:
 *   Zone 1 (HUD): 6 个核心指标大数字 + 脉冲指示灯
 *   Zone 2 (Domains): 6 个 domain 概览卡片
 *   Zone 3 (Main): 左 2/3 活跃任务流 + 右 1/3 需要关注
 *
 * 数据接口不变, 保持 API 兼容
 */
import { useEffect, useState, useCallback, useMemo } from "react";
import {
  listTasks, retryTask, cancelTask, taskSteps, getCommandCenter,
} from "../api";
import type { AgentTask, AgentStep, TaskDisplayItem, TaskCommandCenter } from "../types";
import "./TasksPage.css";

type DomainTab = "all" | "writing" | "deepstudy" | "model" | "discussion" | "memory" | "export" | "failed";

const DOMAIN_KEYS: { key: DomainTab; label: string; icon: string }[] = [
  { key: "writing", label: "写作", icon: "✍" },
  { key: "deepstudy", label: "拆书", icon: "📖" },
  { key: "discussion", label: "讨论", icon: "💬" },
  { key: "memory", label: "记忆", icon: "🧠" },
  { key: "model", label: "模型", icon: "⚡" },
  { key: "export", label: "导出", icon: "📦" },
];

const STREAM_FILTERS: { key: DomainTab; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "writing", label: "写作" },
  { key: "deepstudy", label: "拆书" },
  { key: "failed", label: "失败" },
];

const STAGE_LABELS: Record<string, string> = {
  chapterize: "分章", chapter_profile: "章节画像", entity_extract: "实体抽取",
  event_extract: "事件抽取", scene_beat_extract: "场景节拍", relationship_analyze: "关系分析",
  foreshadow_analyze: "伏笔分析", behavior_pattern_mine: "行为模式", technique_mine: "写作技巧",
  graph_finalize: "图谱整理", study_critic: "质量审查", knowledge_index: "知识索引",
  writing_context_sync: "同步写作",
  planner: "规划", draft: "写作", critic: "评审", reader_feedback: "读者反馈",
  discussion: "讨论", rewrite: "返工", continuity: "连续", learning: "学习", memory_update: "记忆更新",
};

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

function isHiddenInternalTask(task: AgentTask) {
  const kind = (task.task_kind || "").toLowerCase();
  const type_ = (task.task_type || "").toLowerCase();
  if (kind === "deepstudy_run" || type_ === "deepstudy_run") return false;
  if (HIDDEN_TASK_KINDS.has(task.task_kind || "")) return true;
  if (HIDDEN_TASK_TYPES.has(task.task_type || "")) return true;
  return kind.startsWith("deepstudy_stage")
    || kind.startsWith("study_")
    || kind === "study"
    || kind === "study_bulk"
    || kind === "chapterize"
    || kind === "study_material";
}

/* ============================================================
   主组件
   ============================================================ */
export function TasksPage() {
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [cc, setCc] = useState<TaskCommandCenter | null>(null);
  const [streamFilter, setStreamFilter] = useState<DomainTab>("all");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [stepsLoading, setStepsLoading] = useState(false);
  const [busyTaskId, setBusyTaskId] = useState<number | null>(null);
  const [flash, setFlash] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [showInternalEvents, setShowInternalEvents] = useState(false);

  const reload = useCallback(() => {
    Promise.all([
      listTasks({ limit: 100, visibility: "user" }),
      getCommandCenter().catch(() => null),
    ]).then(([taskList, ccData]) => {
      let merged = [...taskList];
      if (ccData && ccData.active) {
        const dsItems = ccData.active.filter(
          (a: TaskDisplayItem) => a.domain === "deepstudy" && a.status === "running"
        );
        for (const dsi of dsItems) {
          if (!merged.some((t) => t.id === dsi.id)) {
            merged.push({
              id: dsi.id, project_id: dsi.project_id ?? 0, chapter_id: dsi.chapter_id,
              task_type: dsi.task_type, status: dsi.status, priority: 100,
              payload: dsi.summary_json ?? {}, error: dsi.error, retry_count: 0,
              cost_usd: dsi.cost_usd, input_tokens: dsi.input_tokens, output_tokens: dsi.output_tokens,
              started_at: dsi.started_at, finished_at: dsi.finished_at, created_at: dsi.created_at,
              domain: dsi.domain, task_kind: dsi.task_kind, material_id: dsi.material_id,
              run_id: dsi.run_id, progress_current: dsi.progress_current,
              progress_total: dsi.progress_total, display_title: dsi.title,
              summary_json: dsi.summary_json,
            } as AgentTask);
          }
        }
      }
      setTasks(merged);
      if (ccData) setCc(ccData);
    }).catch(() => {});
  }, []);

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

  const visibleTasks = useMemo(() => tasks.filter((t) => !isHiddenInternalTask(t)), [tasks]);

  const stats = useMemo(() => ({
    running: visibleTasks.filter((t) => t.status === "running").length,
    pending: visibleTasks.filter((t) => t.status === "pending" || t.status === "queued").length,
    failed: visibleTasks.filter((t) => t.status === "failed").length,
    succeeded: visibleTasks.filter((t) => t.status === "succeeded").length,
    cost: visibleTasks.reduce((s, t) => s + (t.cost_usd || 0), 0),
    tokens: visibleTasks.reduce((s, t) => s + (t.input_tokens || 0) + (t.output_tokens || 0), 0),
  }), [visibleTasks]);

  const userSteps = useMemo(() => steps.filter((s) => s.step_name !== "study_character" && s.step_name !== "study_event"), [steps]);
  const internalSteps = useMemo(() => steps.filter((s) => s.step_name === "study_character" || s.step_name === "study_event"), [steps]);

  // 过滤任务流
  const streamTasks = useMemo(() => {
    if (streamFilter === "all") return visibleTasks;
    if (streamFilter === "failed") return visibleTasks.filter((t) => t.status === "failed");
    return visibleTasks.filter((t) => (t.domain || t.task_type) === streamFilter || (t as any).task_kind?.startsWith(streamFilter));
  }, [visibleTasks, streamFilter]);

  // 需要关注的任务
  const attentionTasks = useMemo(() => visibleTasks.filter((t) => t.status === "failed"), [visibleTasks]);

  // Domain 概览数据
  const domainData = useMemo(() => {
    return DOMAIN_KEYS.map((dk) => {
      const ccDomain = cc?.domains?.find((d) => d.domain === dk.key);
      const domainTasks = visibleTasks.filter((t) => {
        const d = (t.domain || "").toLowerCase();
        return d === dk.key || (t as any).task_kind?.toLowerCase().startsWith(dk.key);
      });
      return {
        key: dk.key,
        label: dk.label,
        icon: dk.icon,
        running: ccDomain?.running ?? domainTasks.filter((t) => t.status === "running").length,
        pending: ccDomain?.pending ?? domainTasks.filter((t) => t.status === "pending" || t.status === "queued").length,
        failed: ccDomain?.failed ?? domainTasks.filter((t) => t.status === "failed").length,
        succeededToday: ccDomain?.succeeded_today ?? 0,
        costToday: ccDomain?.cost_today ?? 0,
        tokensToday: ccDomain?.tokens_today ?? 0,
        currentTitle: ccDomain?.current_title ?? null,
        progressCurrent: ccDomain?.progress_current ?? 0,
        progressTotal: ccDomain?.progress_total ?? 0,
        status: ccDomain?.status ?? (domainTasks.some((t) => t.status === "running") ? "running" : domainTasks.some((t) => t.status === "failed") ? "failed" : "idle"),
      };
    });
  }, [cc, visibleTasks]);

  return (
    <div className="main-body tasks-page">
      {/* Flash */}
      {flash && <div className={`tasks-flash tasks-flash-${flash.type}`}>{flash.text}</div>}

      {/* ============================================================
          ZONE 1 — HUD 核心指标
          ============================================================ */}
      <div className="tasks-hud">
        <div className="tasks-hud-cell" data-active={stats.running > 0 ? "true" : undefined}>
          <span className="tasks-hud-value" data-color="amber">{stats.running}</span>
          <span className="tasks-hud-label">运行中</span>
        </div>
        <div className="tasks-hud-cell">
          <span className="tasks-hud-value">{stats.pending}</span>
          <span className="tasks-hud-label">等待</span>
        </div>
        <div className="tasks-hud-cell" data-alert={stats.failed > 0 ? "true" : undefined}>
          <span className="tasks-hud-value" data-color={stats.failed > 0 ? "red" : undefined}>{stats.failed}</span>
          <span className="tasks-hud-label">失败</span>
        </div>
        <div className="tasks-hud-cell">
          <span className="tasks-hud-value" data-color="green">{stats.succeeded}</span>
          <span className="tasks-hud-label">已完成</span>
        </div>
        <div className="tasks-hud-cell">
          <span className="tasks-hud-value">${stats.cost.toFixed(3)}</span>
          <span className="tasks-hud-label">成本</span>
        </div>
        <div className="tasks-hud-cell">
          <span className="tasks-hud-value" data-color="blue">{(stats.tokens / 1000).toFixed(1)}k</span>
          <span className="tasks-hud-label">Token</span>
        </div>
      </div>

      {/* ============================================================
          ZONE 2 — Domain 概览
          ============================================================ */}
      <div className="tasks-domains">
        {domainData.map((d) => {
          const pct = d.progressTotal > 0 ? Math.min(100, (d.progressCurrent / d.progressTotal) * 100) : 0;
          return (
            <div
              key={d.key}
              className="tasks-domain-card"
              data-status={d.status}
              onClick={() => setStreamFilter(d.key as DomainTab)}
            >
              <div className="tasks-domain-header">
                <span className="tasks-domain-name">{d.icon} {d.label}</span>
                <span className="tasks-domain-badge" data-s={d.status}>
                  {d.status === "running" ? "进行中" : d.status === "failed" ? "失败" : d.succeededToday > 0 ? "已完成" : "空闲"}
                </span>
              </div>
              <div className="tasks-domain-stats">
                <span><span className="num">{d.running}</span> 跑</span>
                <span><span className="num">{d.pending}</span> 等</span>
                <span><span className="num">{d.failed}</span> 败</span>
              </div>
              {d.currentTitle ? (
                <div className="tasks-domain-current">📍 {d.currentTitle}</div>
              ) : (
                <div className="tasks-domain-current" style={{ color: "var(--muted)" }}>—</div>
              )}
              {d.progressTotal > 0 && (
                <div className="tasks-domain-progress">
                  <div className="tasks-domain-progress-fill" style={{ width: `${pct}%` }} />
                </div>
              )}
              <div className="tasks-domain-footer">
                <span>${d.costToday.toFixed(4)}</span>
                <span>{(d.tokensToday / 1000).toFixed(1)}k tok</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* ============================================================
          ZONE 3 — 主区域: 任务流 + 需要关注
          ============================================================ */}
      <div className="tasks-main">
        {/* 左列: 活跃任务流 */}
        <div className="tasks-stream">
          <div className="tasks-stream-header">
            <span className="tasks-stream-title">任务流</span>
            <div className="tasks-stream-filters">
              {STREAM_FILTERS.map((f) => (
                <button
                  key={f.key}
                  className={`tasks-stream-filter ${streamFilter === f.key ? "active" : ""}`}
                  onClick={() => setStreamFilter(f.key)}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
          <div className="tasks-stream-list">
            {streamTasks.length === 0 ? (
              <div className="tasks-empty">暂无任务</div>
            ) : (
              streamTasks.map((t) => {
                const expanded = expandedId === t.id;
                const progressPct = (t.progress_total ?? 0) > 0
                  ? Math.min(100, Math.round(((t.progress_current ?? 0) / (t.progress_total ?? 1)) * 100))
                  : 0;
                const title = t.display_title || `${t.task_type} #${t.id}`;
                const stageLabel = t.stage_key ? (STAGE_LABELS[t.stage_key] || t.stage_key) : "";
                const summary = (t as any).summary_json || {};

                return (
                  <div key={t.id} id={`task-card-${t.id}`}>
                    {/* 任务行 */}
                    <div
                      className={`tasks-task-row ${expanded ? "expanded" : ""}`}
                      onClick={() => setExpandedId(expanded ? null : t.id)}
                    >
                      <span className="tasks-task-dot" data-s={t.status} />
                      <div className="tasks-task-info">
                        <span className="tasks-task-title">{title}</span>
                        <div className="tasks-task-meta">
                          <span className="tasks-pill" data-s={t.status}>{t.status}</span>
                          {stageLabel && <span>{stageLabel}</span>}
                          {t.domain && <span>{t.domain}</span>}
                          {summary && Object.entries(summary).slice(0, 3).map(([k, v]) =>
                            typeof v === "number" && v > 0 ? <span key={k}>{k} {v}</span> : null
                          )}
                        </div>
                      </div>
                      {progressPct > 0 && (
                        <div className="tasks-task-progress-mini">
                          <div className="tasks-task-progress-mini-fill" style={{ width: `${progressPct}%` }} />
                        </div>
                      )}
                      {t.cost_usd > 0 && (
                        <span className="tasks-task-cost">${t.cost_usd.toFixed(4)}</span>
                      )}
                    </div>

                    {/* 展开抽屉 */}
                    {expanded && (
                      <div className="tasks-task-drawer">
                        {/* 错误 */}
                        {t.error && (
                          <div className="tasks-drawer-section">
                            <div className="tasks-drawer-label">错误</div>
                            <pre className="tasks-drawer-error">{t.error}</pre>
                          </div>
                        )}

                        {/* 阶段轨道 */}
                        {t.stage_key && t.progress_total != null && t.progress_total > 0 && (
                          <div className="tasks-drawer-section">
                            <div className="tasks-drawer-label">阶段: {stageLabel}</div>
                            <div className="tasks-task-stage-track">
                              {Array.from({ length: Math.min(14, t.progress_total) }).map((_, i) => (
                                <span
                                  key={i}
                                  className={`tasks-task-stage-dot ${i < (t.progress_current ?? 0) ? "done" : ""}`}
                                />
                              ))}
                            </div>
                          </div>
                        )}

                        {/* 步骤表 */}
                        <div className="tasks-drawer-section">
                          <div className="tasks-drawer-label">步骤 ({userSteps.length})</div>
                          {stepsLoading ? (
                            <div style={{ color: "var(--muted)", fontSize: 11 }}>加载中…</div>
                          ) : userSteps.length === 0 ? (
                            <div style={{ color: "var(--muted)", fontSize: 11 }}>无步骤记录</div>
                          ) : (
                            <table className="tasks-steps-table">
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
                                    <td style={{ fontFamily: "var(--font-mono, monospace)" }}>{s.step_name}</td>
                                    <td>{s.agent_name}</td>
                                    <td><span className="tasks-pill" data-s={s.status}>{s.status}</span></td>
                                    <td>{s.model_name ?? "—"}</td>
                                    <td style={{ textAlign: "right", fontFamily: "var(--font-mono, monospace)" }}>{s.duration_ms}ms</td>
                                    <td style={{ textAlign: "right", fontFamily: "var(--font-mono, monospace)" }}>${s.cost_usd.toFixed(4)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                        </div>

                        {/* 内部事件 */}
                        {internalSteps.length > 0 && (
                          <div className="tasks-drawer-section">
                            <button
                              className="tasks-internal-toggle"
                              onClick={(e) => { e.stopPropagation(); setShowInternalEvents(!showInternalEvents); }}
                            >
                              {showInternalEvents ? "收起" : "展开"} 内部事件 ({internalSteps.length})
                            </button>
                            {showInternalEvents && (
                              <div className="tasks-internal-list">
                                {internalSteps.map((s) => (
                                  <div key={s.id} className="tasks-internal-row">
                                    <span className="tasks-pill" data-s={s.status}>{s.status}</span>
                                    {" "}{s.step_name} · {s.agent_name}
                                    {s.duration_ms ? ` · ${s.duration_ms}ms` : ""}
                                    {s.cost_usd ? ` · $${s.cost_usd.toFixed(4)}` : ""}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}

                        {/* 操作栏 */}
                        <div className="tasks-drawer-actions">
                          <span className="tasks-drawer-time">
                            {t.started_at ? new Date(t.started_at).toLocaleString() : "—"}
                            {" → "}
                            {t.finished_at ? new Date(t.finished_at).toLocaleString() : "运行中"}
                          </span>
                          <span style={{ flex: 1 }} />
                          {t.status === "failed" && (
                            <button
                              className="tasks-btn" data-variant="primary"
                              onClick={(e) => { e.stopPropagation(); doRetry(t); }}
                              disabled={busyTaskId === t.id}
                            >
                              {busyTaskId === t.id ? "..." : "重试"}
                            </button>
                          )}
                          {(t.status === "pending" || t.status === "running" || t.status === "queued") && (
                            <button
                              className="tasks-btn" data-variant="danger"
                              onClick={(e) => { e.stopPropagation(); doCancel(t); }}
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

        {/* 右列: 需要关注 */}
        <div className="tasks-attention">
          <div className="tasks-attention-header">
            <span className="tasks-attention-title">需要关注</span>
            <span className="tasks-attention-count" data-has={attentionTasks.length > 0 ? "true" : "false"}>
              {attentionTasks.length}
            </span>
          </div>
          <div className="tasks-attention-list">
            {attentionTasks.length === 0 ? (
              <div className="tasks-empty">✓ 一切正常</div>
            ) : (
              attentionTasks.map((t) => (
                <div key={t.id} className="tasks-attention-item">
                  <span className="tasks-attention-item-title">
                    {t.display_title || `${t.task_type} #${t.id}`}
                  </span>
                  {t.error && (
                    <span className="tasks-attention-item-error">{t.error}</span>
                  )}
                  <div className="tasks-attention-item-actions">
                    <button
                      className="tasks-btn" data-variant="primary"
                      onClick={() => doRetry(t)}
                      disabled={busyTaskId === t.id}
                    >
                      {busyTaskId === t.id ? "..." : "重试"}
                    </button>
                    <button
                      className="tasks-btn" data-variant="danger"
                      onClick={() => setExpandedId(t.id)}
                    >
                      详情
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
