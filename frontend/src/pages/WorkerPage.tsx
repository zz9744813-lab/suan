import { useEffect, useState } from "react";
import { useWorkerStore } from "../stores/workerStore";
import { workerStart, workerPause, workerResume, workerStop, listTasks } from "../api";
import type { AgentTask } from "../types";

export function WorkerPage() {
  const status = useWorkerStore((s) => s.status);
  const refresh = useWorkerStore((s) => s.refresh);
  const [tasks, setTasks] = useState<AgentTask[]>([]);

  useEffect(() => {
    const load = () => {
      listTasks({ limit: 30 }).then(setTasks).catch(() => {});
    };
    load();
    const t = window.setInterval(load, 3000);
    return () => window.clearInterval(t);
  }, []);

  const running = status?.state === "running";
  const paused = status?.state === "paused";
  const stopped = status?.state === "stopped" || status?.state === "idle";

  return (
    <div className="main-body">
      <div className="page-header">
        <div>
          <h1>Worker</h1>
          <div className="sub">24 小时续写器：负责从 agent_tasks 队列中取任务、跑流水线、记账。</div>
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
          <div className="label">状态</div>
          <div className="num" style={{ color: status?.state === "running" ? "var(--state-ok)" : status?.state === "paused" ? "var(--accent-gold)" : "var(--text-muted)" }}>
            {status?.state ?? "—"}
          </div>
          <div className="sub">{status?.is_loop_alive ? "循环活着" : "循环已停"}</div>
        </div>
        <div className="stat">
          <div className="label">今日字数</div>
          <div className="num">{(status?.today_words ?? 0).toLocaleString()}</div>
        </div>
        <div className="stat">
          <div className="label">今日成本</div>
          <div className="num">${(status?.today_cost_usd ?? 0).toFixed(3)}</div>
        </div>
        <div className="stat">
          <div className="label">连续失败</div>
          <div className="num" style={{ color: (status?.consecutive_failures ?? 0) > 0 ? "var(--state-warn)" : undefined }}>
            {status?.consecutive_failures ?? 0}
          </div>
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

      <div className="card">
        <h3>任务队列（最近 30 条）</h3>
        {tasks.length === 0 ? (
          <div className="muted">还没有任务。</div>
        ) : (
          <table>
            <thead>
              <tr><th>#</th><th>类型</th><th>项目/章节</th><th>状态</th><th style={{ textAlign: "right" }}>成本</th><th>时间</th></tr>
            </thead>
            <tbody>
              {tasks.map((t) => (
                <tr key={t.id}>
                  <td className="mono muted">{t.id}</td>
                  <td>{t.task_type}</td>
                  <td className="small muted">项目 {t.project_id} / 章节 {t.chapter_id ?? "—"}</td>
                  <td><span className={`pill ${t.status}`}>{t.status}</span></td>
                  <td className="mono" style={{ textAlign: "right" }}>${t.cost_usd.toFixed(4)}</td>
                  <td className="muted tiny">{new Date(t.created_at).toLocaleString("zh-CN")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
