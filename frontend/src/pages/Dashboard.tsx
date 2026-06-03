import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useProjectStore } from "../stores/projectStore";
import { useWorkerStore } from "../stores/workerStore";
import { useEventStore } from "../stores/eventStore";
import { listTasks, workerStart, workerPause, workerResume, workerStop, getDefaultPolicy } from "../api";
import type { AgentTask, WorkerPolicy } from "../types";
import "./Dashboard.css";

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
            <span className="muted small">{events.length} 条</span>
          </div>
          <div className="event-feed">
            {events.length === 0 ? (
              <div className="empty">等待事件…</div>
            ) : (
              [...events].reverse().slice(0, 50).map((e) => (
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
