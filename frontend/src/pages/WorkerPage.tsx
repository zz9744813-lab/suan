import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { workerStart, workerPause, workerResume, workerStop, listTasks } from "../api";
import { PolicyPresetsCard } from "../components/worker/PolicyPresetsCard";
import { useWorkerStore } from "../stores/workerStore";
import type { AgentTask } from "../types";

function progressPct(task: AgentTask) {
  const total = task.progress_total ?? 0;
  if (total <= 0) return task.status === "succeeded" ? 100 : 0;
  return Math.min(100, Math.round(((task.progress_current ?? 0) / total) * 100));
}

function taskTitle(task: AgentTask) {
  return task.display_title || task.summary_json?.title || task.task_kind || task.task_type;
}

function bookKey(task: AgentTask) {
  if (task.project_id) return `project:${task.project_id}`;
  if (task.material_id) return `material:${task.material_id}`;
  return "unassigned";
}

function bookLabel(task: AgentTask) {
  const payloadTitle = task.payload?.book_title || task.payload?.project_name || task.summary_json?.book_title;
  if (payloadTitle) return String(payloadTitle);
  if (task.project_id) return `项目 #${task.project_id}`;
  if (task.material_id) return `素材 #${task.material_id}`;
  return "未绑定作品";
}

function isProductionTask(task: AgentTask) {
  const domain = task.domain || "writing";
  const kind = task.task_kind || task.task_type;
  if (domain === "deepstudy" || kind?.startsWith("deepstudy")) return false;
  if (kind === "study" || kind === "study_bulk") return false;
  return true;
}

function statusCount(tasks: AgentTask[], status: string) {
  return tasks.filter((task) => task.status === status).length;
}

export function WorkerPage() {
  const status = useWorkerStore((s) => s.status);
  const refresh = useWorkerStore((s) => s.refresh);
  const [tasks, setTasks] = useState<AgentTask[]>([]);

  useEffect(() => {
    const load = () => {
      listTasks({ limit: 100, visibility: "user" }).then(setTasks).catch(() => {});
    };
    load();
    const t = window.setInterval(load, 5000);
    return () => window.clearInterval(t);
  }, []);

  const productionTasks = useMemo(() => tasks.filter(isProductionTask), [tasks]);
  const grouped = useMemo(() => {
    const map = new Map<string, { label: string; tasks: AgentTask[] }>();
    for (const task of productionTasks) {
      const key = bookKey(task);
      const group = map.get(key) || { label: bookLabel(task), tasks: [] };
      group.tasks.push(task);
      map.set(key, group);
    }
    return Array.from(map.entries()).map(([key, group]) => ({
      key,
      label: group.label,
      tasks: group.tasks.sort((a, b) => b.id - a.id),
    }));
  }, [productionTasks]);

  const running = status?.state === "running";
  const paused = status?.state === "paused";
  const stopped = status?.state === "stopped" || status?.state === "idle";
  const totalCost = productionTasks.reduce((sum, task) => sum + (task.cost_usd || 0), 0);
  const totalTokens = productionTasks.reduce((sum, task) => sum + (task.input_tokens || 0) + (task.output_tokens || 0), 0);

  return (
    <div className="main-body">
      <div className="page-header">
        <div>
          <h1>生产任务</h1>
          <div className="sub">按作品归档章节生产任务；拆书进度在书架详情里查看。</div>
        </div>
        <div className="actions">
          {!running && <button className="primary" onClick={async () => { await workerStart(); refresh(); }}>启动</button>}
          {running && <button onClick={async () => { await workerPause(); refresh(); }}>暂停</button>}
          {paused && <button className="primary" onClick={async () => { await workerResume(); refresh(); }}>恢复</button>}
          {!stopped && <button className="danger" onClick={async () => { await workerStop(); refresh(); }}>停止</button>}
        </div>
      </div>

      <div className="stat-grid">
        <div className="stat">
          <div className="label">Worker 状态</div>
          <div className="num" style={{ color: status?.state === "running" ? "var(--state-ok)" : status?.state === "paused" ? "var(--accent-gold)" : "var(--text-muted)" }}>
            {status?.state ?? "-"}
          </div>
          <div className="sub">{status?.is_loop_alive ? "循环在线" : "循环未运行"}</div>
        </div>
        <div className="stat">
          <div className="label">生产队列</div>
          <div className="num">{statusCount(productionTasks, "pending")} / {statusCount(productionTasks, "running")}</div>
          <div className="sub">排队 / 运行</div>
        </div>
        <div className="stat">
          <div className="label">近期待完成</div>
          <div className="num">{statusCount(productionTasks, "failed")} / {statusCount(productionTasks, "succeeded")}</div>
          <div className="sub">失败 / 成功</div>
        </div>
        <div className="stat">
          <div className="label">生产消耗</div>
          <div className="num">${totalCost.toFixed(3)}</div>
          <div className="sub">{(totalTokens / 1000).toFixed(1)}k tokens</div>
        </div>
      </div>

      {status?.last_error && (
        <div className="card">
          <h3>最近错误</h3>
          <pre className="mono tiny" style={{ background: "var(--bg-rail)", padding: 12, borderRadius: 4, color: "var(--state-error)", whiteSpace: "pre-wrap" }}>
            {status.last_error}
          </pre>
        </div>
      )}

      <PolicyPresetsCard />

      <section className="card">
        <div className="card-header">
          <h3>作品生产看板</h3>
          <Link className="ghost" to="/study/library">查看拆书书架</Link>
        </div>
        {grouped.length === 0 ? (
          <div className="muted">暂无写作生产任务。拆书任务不会显示在这里。</div>
        ) : (
          <div style={{ display: "grid", gap: 14 }}>
            {grouped.map((group) => {
              const groupCost = group.tasks.reduce((sum, task) => sum + (task.cost_usd || 0), 0);
              const groupTokens = group.tasks.reduce((sum, task) => sum + (task.input_tokens || 0) + (task.output_tokens || 0), 0);
              return (
                <div
                  key={group.key}
                  style={{
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    padding: 14,
                    background: "var(--bg-rail)",
                  }}
                >
                  <div className="card-header">
                    <div>
                      <h3>{group.label}</h3>
                      <div className="muted small">
                        {group.tasks.length} 个生产任务 · 运行 {statusCount(group.tasks, "running")} · 失败 {statusCount(group.tasks, "failed")}
                      </div>
                    </div>
                    <div className="mono tiny muted">${groupCost.toFixed(4)} · {(groupTokens / 1000).toFixed(1)}k tok</div>
                  </div>
                  <table>
                    <thead>
                      <tr>
                        <th>章节/任务</th>
                        <th>状态</th>
                        <th>进度</th>
                        <th style={{ textAlign: "right" }}>优先级</th>
                        <th style={{ textAlign: "right" }}>消耗</th>
                        <th>错误</th>
                      </tr>
                    </thead>
                    <tbody>
                      {group.tasks.map((task) => {
                        const pct = progressPct(task);
                        return (
                          <tr key={task.id}>
                            <td>
                              <div>{taskTitle(task)}</div>
                              <div className="tiny muted">任务 #{task.id} · 章节 {task.chapter_id ?? "-"}</div>
                            </td>
                            <td><span className={`pill ${task.status}`}>{task.status}</span></td>
                            <td style={{ minWidth: 130 }}>
                              <div className="progress" style={{ height: 4 }}>
                                <div className="fill" style={{ width: `${pct}%` }} />
                              </div>
                              <div className="tiny muted">{task.progress_current ?? 0} / {task.progress_total ?? 0}</div>
                            </td>
                            <td className="mono" style={{ textAlign: "right" }}>{task.priority}</td>
                            <td className="mono" style={{ textAlign: "right" }}>
                              ${task.cost_usd.toFixed(4)}
                              <div className="tiny muted">{((task.input_tokens + task.output_tokens) / 1000).toFixed(1)}k tok</div>
                            </td>
                            <td className="tiny error">{task.error || ""}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
