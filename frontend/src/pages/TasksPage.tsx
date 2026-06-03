/**
 * TasksPage — 任务列表 (Round 13, P0-UI-7)
 *
 * 之前只有筛选+表格,现在补上:
 *   - failed 任务显示「重试」按钮 (调 retryTask, mode=full)
 *   - pending/running 任务显示「取消」按钮 (调 cancelTask)
 *   - 点击行展开: 显示 error_message + step 列表
 *   - filter chip 改成可点击的按钮组 (全/运行/失败/已成功)
 *
 * 不动 backend。
 */
import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import {
  listTasks, retryTask, cancelTask, taskSteps,
} from "../api";
import type { AgentTask, AgentStep } from "../types";
import "./TasksPage.css";

type Filter = "all" | "running" | "failed" | "succeeded";

const FILTERS: { key: Filter; label: string; cls: string }[] = [
  { key: "all",       label: "全部",   cls: "" },
  { key: "running",   label: "运行中", cls: "running" },
  { key: "failed",    label: "失败",   cls: "failed" },
  { key: "succeeded", label: "已成功", cls: "succeeded" },
];

const STATUS_FILTER_MAP: Record<Filter, string | undefined> = {
  all: undefined,
  running: "running",
  failed: "failed",
  succeeded: "succeeded",
};

export function TasksPage() {
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [stepsLoading, setStepsLoading] = useState(false);
  const [busyTaskId, setBusyTaskId] = useState<number | null>(null);
  const [flash, setFlash] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  const reload = useCallback(() => {
    listTasks({ limit: 100, status: STATUS_FILTER_MAP[filter] }).then(setTasks).catch(() => {});
  }, [filter]);

  useEffect(() => {
    reload();
    const t = window.setInterval(reload, 3000);
    return () => window.clearInterval(t);
  }, [reload]);

  // Expand row → fetch steps lazily
  useEffect(() => {
    if (expandedId == null) { setSteps([]); return; }
    setStepsLoading(true);
    taskSteps(expandedId)
      .then((s) => setSteps(s))
      .catch(() => setSteps([]))
      .finally(() => setStepsLoading(false));
  }, [expandedId]);

  async function doRetry(t: AgentTask) {
    if (!confirm(`重试任务 #${t.id} (${t.task_type})?\n\n会用同样的 payload 重新跑一遍。`)) return;
    setBusyTaskId(t.id); setFlash(null);
    try {
      await retryTask(t.id, { mode: "full" });
      setFlash({ type: "ok", text: `任务 #${t.id} 已重新入队` });
      reload();
    } catch (e: any) {
      setFlash({ type: "err", text: `重试失败: ${e.message}` });
    } finally {
      setBusyTaskId(null);
      setTimeout(() => setFlash(null), 3000);
    }
  }

  async function doCancel(t: AgentTask) {
    if (!confirm(`取消任务 #${t.id}?\n\n只能取消 pending / running 状态的任务。`)) return;
    setBusyTaskId(t.id); setFlash(null);
    try {
      await cancelTask(t.id);
      setFlash({ type: "ok", text: `任务 #${t.id} 已取消` });
      reload();
    } catch (e: any) {
      setFlash({ type: "err", text: `取消失败: ${e.message}` });
    } finally {
      setBusyTaskId(null);
      setTimeout(() => setFlash(null), 3000);
    }
  }

  // counts for the filter chips
  const counts = {
    all: tasks.length, // only the current filter scope, just to show numbers
    running: tasks.filter((t) => t.status === "running").length,
    failed: tasks.filter((t) => t.status === "failed").length,
    succeeded: tasks.filter((t) => t.status === "succeeded").length,
  };

  return (
    <div className="main-body tasks-page">
      <div className="page-header">
        <div>
          <h1>任务</h1>
          <div className="sub">所有 agent_tasks 记录 · 失败可重试 · 展开看错误与步骤</div>
        </div>
      </div>

      <div className="tasks-filter-row">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            className={`tasks-filter-chip ${filter === f.key ? "active" : ""}`}
            onClick={() => setFilter(f.key)}
          >
            <span className="chip-label">{f.label}</span>
            <span className="chip-count">{counts[f.key]}</span>
          </button>
        ))}
      </div>

      {flash && (
        <div className={`tasks-flash tasks-flash-${flash.type}`}>{flash.text}</div>
      )}

      <div className="card">
        {tasks.length === 0 ? (
          <div className="muted">还没有任务。点「项目」→ 章节「开始流水线」可新建任务。</div>
        ) : (
          <table className="tasks-table">
            <thead>
              <tr>
                <th style={{ width: 30 }}></th>
                <th>#</th><th>类型</th><th>项目</th><th>章节</th>
                <th>状态</th><th>优先级</th>
                <th style={{ textAlign: "right" }}>成本</th>
                <th style={{ textAlign: "right" }}>Tokens</th>
                <th>开始 / 完成</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((t) => {
                const expanded = expandedId === t.id;
                return (
                  <>
                    <tr
                      key={t.id}
                      className={`${expanded ? "expanded" : ""} ${t.status === "failed" ? "is-failed" : ""}`}
                      onClick={() => setExpandedId(expanded ? null : t.id)}
                      style={{ cursor: "pointer" }}
                    >
                      <td className="expand-caret">{expanded ? "▼" : "▶"}</td>
                      <td className="mono muted">{t.id}</td>
                      <td>{t.task_type}</td>
                      <td><Link to={`/projects/${t.project_id}`} onClick={(e) => e.stopPropagation()}>#{t.project_id}</Link></td>
                      <td>{t.chapter_id ? <Link to={`/projects/${t.project_id}/chapters/${t.chapter_id}`} onClick={(e) => e.stopPropagation()}>第 {t.chapter_id} 章</Link> : "—"}</td>
                      <td><span className={`pill ${t.status}`}>{t.status}</span></td>
                      <td className="mono">{t.priority}</td>
                      <td className="mono" style={{ textAlign: "right" }}>${t.cost_usd.toFixed(4)}</td>
                      <td className="mono muted" style={{ textAlign: "right" }}>{(t.input_tokens / 1000).toFixed(1)}k / {(t.output_tokens / 1000).toFixed(1)}k</td>
                      <td className="muted tiny">
                        {t.started_at ? new Date(t.started_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }) : "—"}
                        {" / "}
                        {t.finished_at ? new Date(t.finished_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }) : "—"}
                      </td>
                      <td className="task-actions" onClick={(e) => e.stopPropagation()}>
                        {t.status === "failed" && (
                          <button
                            className="link retry"
                            onClick={() => doRetry(t)}
                            disabled={busyTaskId === t.id}
                          >
                            {busyTaskId === t.id ? "..." : "重试"}
                          </button>
                        )}
                        {(t.status === "pending" || t.status === "running") && (
                          <button
                            className="link cancel"
                            onClick={() => doCancel(t)}
                            disabled={busyTaskId === t.id}
                          >
                            {busyTaskId === t.id ? "..." : "取消"}
                          </button>
                        )}
                      </td>
                    </tr>
                    {expanded && (
                      <tr key={`${t.id}-detail`} className="detail-row">
                        <td colSpan={11}>
                          <div className="tasks-detail">
                            {t.error && (
                              <div className="tasks-detail-block">
                                <div className="detail-title">错误</div>
                                <pre className="error-text">{t.error}</pre>
                              </div>
                            )}
                            <div className="tasks-detail-block">
                              <div className="detail-title">步骤 ({steps.length})</div>
                              {stepsLoading ? (
                                <div className="muted small">加载步骤…</div>
                              ) : steps.length === 0 ? (
                                <div className="muted small">无步骤记录 (可能事务已回滚)。</div>
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
                                    {steps.map((s) => (
                                      <tr key={s.id}>
                                        <td className="mono small">{s.step_name}</td>
                                        <td className="muted small">{s.agent_name}</td>
                                        <td><span className={`pill ${s.status === "succeeded" ? "succeeded" : s.status === "failed" ? "failed" : ""}`}>{s.status}</span></td>
                                        <td className="muted tiny">{s.model_name ?? "—"}</td>
                                        <td className="mono tiny" style={{ textAlign: "right" }}>{s.duration_ms}ms</td>
                                        <td className="mono tiny" style={{ textAlign: "right" }}>${s.cost_usd.toFixed(4)}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              )}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
