import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listTasks } from "../api";
import type { AgentTask } from "../types";

export function TasksPage() {
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [status, setStatus] = useState<string>("");

  useEffect(() => {
    const load = () => {
      listTasks({ limit: 100, status: status || undefined }).then(setTasks).catch(() => {});
    };
    load();
    const t = window.setInterval(load, 3000);
    return () => window.clearInterval(t);
  }, [status]);

  return (
    <div className="main-body">
      <div className="page-header">
        <div>
          <h1>任务</h1>
          <div className="sub">所有 agent_tasks 记录。失败的任务可以点重试。</div>
        </div>
        <div className="actions">
          <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ width: 160 }}>
            <option value="">全部状态</option>
            <option value="pending">pending</option>
            <option value="running">running</option>
            <option value="succeeded">succeeded</option>
            <option value="failed">failed</option>
            <option value="cancelled">cancelled</option>
          </select>
        </div>
      </div>

      <div className="card">
        {tasks.length === 0 ? (
          <div className="muted">还没有任务。</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>#</th><th>类型</th><th>项目</th><th>章节</th>
                <th>状态</th><th>优先级</th>
                <th style={{ textAlign: "right" }}>成本</th>
                <th style={{ textAlign: "right" }}>Tokens</th>
                <th>开始 / 完成</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((t) => (
                <tr key={t.id}>
                  <td className="mono muted">{t.id}</td>
                  <td>{t.task_type}</td>
                  <td><Link to={`/projects/${t.project_id}`}>#{t.project_id}</Link></td>
                  <td>{t.chapter_id ? <Link to={`/projects/${t.project_id}/chapters/${t.chapter_id}`}>第 {t.chapter_id} 章</Link> : "—"}</td>
                  <td><span className={`pill ${t.status}`}>{t.status}</span></td>
                  <td className="mono">{t.priority}</td>
                  <td className="mono" style={{ textAlign: "right" }}>${t.cost_usd.toFixed(4)}</td>
                  <td className="mono muted" style={{ textAlign: "right" }}>{(t.input_tokens / 1000).toFixed(1)}k / {(t.output_tokens / 1000).toFixed(1)}k</td>
                  <td className="muted tiny">
                    {t.started_at ? new Date(t.started_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }) : "—"}
                    {" / "}
                    {t.finished_at ? new Date(t.finished_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
