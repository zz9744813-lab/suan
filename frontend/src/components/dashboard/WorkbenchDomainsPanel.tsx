/**
 * WorkbenchDomainsPanel — 五域生产状态面板 (P0 返工 §0.1)
 *
 * 替代原来横向的 AgentPipelineVisualization。
 * 数据源：GET /api/workbench/live-state
 *
 * 显示 5 张状态卡 (写作 / 拆书 / 模型 / 讨论 / 记忆)，
 * 每张卡片显示该域的当前动作 + 进度 + 摘要 + 错误。
 */
import { useEffect, useState } from "react";
import { getLiveState } from "../../api";
import type { WorkbenchLiveState, WorkbenchDomainState } from "../../types";

const DOMAIN_ORDER = ["writing", "deepstudy", "model", "discussion", "memory"];

function statusBadge(s: WorkbenchDomainState["status"]) {
  if (s === "running") return { txt: "运行中", cls: "ok" };
  if (s === "failed") return { txt: "失败", cls: "error" };
  if (s === "blocked") return { txt: "堵塞", cls: "warn" };
  return { txt: "空闲", cls: "muted" };
}

export function WorkbenchDomainsPanel() {
  const [data, setData] = useState<WorkbenchLiveState | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      getLiveState()
        .then((d) => { if (!cancelled) { setData(d); setErr(null); } })
        .catch((e) => { if (!cancelled) setErr(String(e?.message ?? e)); });
    };
    tick();
    const t = window.setInterval(tick, 4000);
    return () => { cancelled = true; window.clearInterval(t); };
  }, []);

  if (err) {
    return (
      <section className="dashboard-card">
        <div className="card-header"><h3>五域生产状态</h3></div>
        <div className="muted small" style={{ padding: 12 }}>加载失败：{err}</div>
      </section>
    );
  }
  if (!data) {
    return (
      <section className="dashboard-card">
        <div className="card-header"><h3>五域生产状态</h3></div>
        <div className="muted small" style={{ padding: 12 }}>加载中…</div>
      </section>
    );
  }

  return (
    <section className="dashboard-card workbench-domains">
      <div className="card-header">
        <h3>五域生产状态</h3>
        <span className="muted small">
          {data.main_task
            ? `主任务 #${data.main_task.id} · ${data.main_task.title}`
            : "当前无主任务"}
        </span>
      </div>
      <div className="workbench-domains-grid">
        {DOMAIN_ORDER.map((key) => {
          const d = data.domains[key];
          if (!d) return null;
          const badge = statusBadge(d.status);
          return (
            <div key={key} className={`workbench-domain-card status-${d.status}`}>
              <div className="workbench-domain-head">
                <span className="workbench-domain-icon">{d.icon}</span>
                <span className="workbench-domain-label">{d.label}</span>
                <span className={`pill tiny ${badge.cls}`}>{badge.txt}</span>
              </div>
              <div className="workbench-domain-action">
                {d.current_action || "暂无任务"}
              </div>
              {d.progress != null && d.progress > 0 && (
                <div className="workbench-domain-progress">
                  <div className="workbench-domain-progress-fill" style={{ width: `${d.progress}%` }} />
                  <span className="muted tiny">{d.progress}%</span>
                </div>
              )}
              <div className="workbench-domain-meta">
                <span className="muted tiny">{d.current_agent}</span>
                {d.artifact_summary && d.artifact_summary !== "—" && (
                  <span className="muted tiny">· {d.artifact_summary}</span>
                )}
              </div>
              {d.error && (
                <div className="workbench-domain-error">{d.error}</div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
