import { useEffect, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useSSE } from "../hooks/useSSE";
import { useProjectStore } from "../stores/projectStore";
import { useWorkerStore } from "../stores/workerStore";
import { useChiefStore } from "../stores/chiefStore";
import { ChiefAgentPanel } from "./ChiefAgentPanel";
import "./AppShell.css";

type Props = { children: ReactNode };

// 4-zone layout per UI/UX spec:
//   ┌──[Rail]──[ProjectNav]──[Main content]──[ChiefAgent]──┐
//   │              │            │                │           │
//   │  icon nav    │  list      │  pages         │  right    │
//   │  56px        │  260px     │  flex          │  380px    │
//   └───────────────────────────────────────────────────────┘
//   [Status bar — 28px]
export function AppShell({ children }: Props) {
  useSSE();
  const refreshProjects = useProjectStore((s) => s.refresh);
  const projects = useProjectStore((s) => s.projects);
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const selectProject = useProjectStore((s) => s.selectProject);

  const startWorkerPolling = useWorkerStore((s) => s.startPolling);
  const workerState = useWorkerStore((s) => s.status?.state ?? "idle");
  const todayWords = useWorkerStore((s) => s.status?.today_words ?? 0);
  const todayCost = useWorkerStore((s) => s.status?.today_cost_usd ?? 0);
  const lastError = useWorkerStore((s) => s.status?.last_error ?? null);

  const chiefReset = useChiefStore((s) => s.reset);
  const location = useLocation();
  const isChiefVisible = location.pathname.startsWith("/dashboard")
    || location.pathname.startsWith("/projects");

  useEffect(() => {
    refreshProjects();
  }, [refreshProjects]);

  useEffect(() => {
    startWorkerPolling();
  }, [startWorkerPolling]);

  useEffect(() => {
    // Reset chief session when the project changes so the panel pulls a
    // fresh conversation.
    chiefReset();
  }, [currentProjectId, chiefReset]);

  const currentProject = projects.find((p) => p.id === currentProjectId);

  return (
    <div className="shell">
      {/* === Rail (leftmost, 56px) === */}
      <nav className="rail">
        <div className="rail-brand" title="NovelForge 2.0">NF</div>
        <div className="rail-spacer" />
        <RailItem to="/dashboard" label="工作台" icon="◧" />
        <RailItem to="/projects" label="项目" icon="≡" />
        <RailItem to="/tasks" label="任务" icon="▤" />
        <RailItem to="/worker" label="Worker" icon="▶" />
        <div className="rail-divider" />
        <RailItem to="/prompts" label="Prompt" icon="✎" />
        <RailItem to="/models" label="模型" icon="◈" />
        <div className="rail-spacer" />
        <div className={`rail-dot rail-dot-${stateColor(workerState)}`} title={`Worker: ${workerState}`} />
      </nav>

      {/* === ProjectNav (260px) === */}
      <aside className="projectnav">
        <div className="projectnav-header">
          <span className="projectnav-title">项目</span>
          <NavLink to="/projects" className="projectnav-add" title="管理项目">+</NavLink>
        </div>
        <div className="projectnav-list">
          {projects.length === 0 ? (
            <div className="projectnav-empty">
              还没有项目。<br />
              <NavLink to="/projects" className="gold">新建一个</NavLink>
            </div>
          ) : (
            projects.map((p) => (
              <button
                key={p.id}
                className={`projectnav-item ${p.id === currentProjectId ? "active" : ""}`}
                onClick={() => selectProject(p.id)}
              >
                <div className="projectnav-item-name ellipsis">{p.name}</div>
                <div className="projectnav-item-meta">
                  <span className="badge gold tiny">{p.genre}</span>
                  <span className="tiny muted">{p.chapter_count}章 · {formatNumber(p.total_words)}字</span>
                </div>
                <div className="projectnav-item-bar">
                  <div
                    className="projectnav-item-bar-fill"
                    style={{ width: `${Math.min(100, (p.total_words / p.target_word_count) * 100)}%` }}
                  />
                </div>
              </button>
            ))
          )}
        </div>
        {currentProject && (
          <div className="projectnav-footer">
            <div className="row small">
              <span className="muted">目标</span>
              <span className="spacer" />
              <span className="mono">{formatNumber(currentProject.target_word_count)}字 / {currentProject.target_chapter_count}章</span>
            </div>
          </div>
        )}
      </aside>

      {/* === Main content === */}
      <main className="main">{children}</main>

      {/* === ChiefAgent (380px, right) === */}
      {isChiefVisible && <ChiefAgentPanel projectId={currentProjectId} />}

      {/* === StatusBar (28px) === */}
      <footer className="statusbar">
        <span className={`status-dot status-dot-${stateColor(workerState)}`} />
        <span>Worker: <b>{workerState}</b></span>
        <span className="status-sep" />
        <span>今日 <b className="mono">{formatNumber(todayWords)}</b> 字</span>
        <span className="status-sep" />
        <span>今日成本 <b className="mono">${todayCost.toFixed(3)}</b></span>
        {lastError && (
          <>
            <span className="status-sep" />
            <span className="error ellipsis" title={lastError}>最近错误：{lastError.slice(0, 60)}</span>
          </>
        )}
        <span className="spacer" />
        {currentProject ? (
          <span>当前项目：<b className="gold">{currentProject.name}</b></span>
        ) : (
          <span className="muted">未选择项目</span>
        )}
      </footer>
    </div>
  );
}

function RailItem({ to, label, icon }: { to: string; label: string; icon: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) => `rail-item ${isActive ? "active" : ""}`}
      title={label}
    >
      <span className="rail-item-icon">{icon}</span>
      <span className="rail-item-label">{label}</span>
    </NavLink>
  );
}

function stateColor(state: string): "ok" | "warn" | "error" | "info" {
  if (state === "running") return "ok";
  if (state === "paused" || state === "paused_budget") return "warn";
  if (state === "error" || state === "stopped") return "error";
  return "info";
}

function formatNumber(n: number): string {
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`;
  return n.toLocaleString();
}
