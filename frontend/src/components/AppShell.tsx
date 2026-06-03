import { useEffect, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useSSE } from "../hooks/useSSE";
import { useProjectStore } from "../stores/projectStore";
import { useWorkerStore } from "../stores/workerStore";
import { useChiefStore } from "../stores/chiefStore";
import { useLayoutStore } from "../stores/layoutStore";
import { ChiefAgentPanel } from "./ChiefAgentPanel";
import { ProjectNav } from "./project/ProjectNav";
import { RailNav } from "./layout/RailNav";
import { BottomStatusBar } from "./layout/BottomStatusBar";
import { GlobalSearch } from "./layout/GlobalSearch";
import { formatThousands } from "../lib/format";
import "./AppShell.css";

type Props = { children: ReactNode };

// R6 + R7: 4-zone responsive grid with three-mode side panels.
//   ┌──[RailNav]──[ProjectNav]──[Main]──[ChiefPanel]──┐
//   └──────────────[BottomStatusBar]──────────────────┘
//
// R6 introduced the Concept B color tokens (light main, dark rail).
// R7 extracted the rail + status bar into their own components;
// AppShell now only handles the grid + project library + chief panel
// mounting.
export function AppShell({ children }: Props) {
  useSSE();
  const refreshProjects = useProjectStore((s) => s.refresh);
  const projects = useProjectStore((s) => s.projects);
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const selectProject = useProjectStore((s) => s.selectProject);

  const startWorkerPolling = useWorkerStore((s) => s.startPolling);

  const chiefReset = useChiefStore((s) => s.reset);

  const projectNavMode = useLayoutStore((s) => s.projectNavMode);
  const chiefPanelMode = useLayoutStore((s) => s.chiefPanelMode);
  const setChiefPanelMode = useLayoutStore((s) => s.setChiefPanelMode);
  const setProjectNavMode = useLayoutStore((s) => s.setProjectNavMode);
  const cycleProjectNav = useLayoutStore((s) => s.cycleProjectNav);
  const cycleChiefPanel = useLayoutStore((s) => s.cycleChiefPanel);

  const location = useLocation();
  // R15 / P0-CHIEF-1: ChiefAgent is now globally available on every
  // route. The user's panel mode (expanded / compact / hidden) is
  // respected everywhere; we no longer force-hide it on /tasks,
  // /worker, /models, /prompts, /study, /memory, /discussion. The
  // panel receives `pageContext` so its quick-commands can change
  // based on the current page.
  const chiefMode = chiefPanelMode;

  useEffect(() => { refreshProjects(); }, [refreshProjects]);
  useEffect(() => { startWorkerPolling(); }, [startWorkerPolling]);
  useEffect(() => {
    chiefReset();
  }, [currentProjectId, chiefReset]);

  const currentProject = projects.find((p) => p.id === currentProjectId);

  const shellClass = [
    "app-shell",
    "shell",
    `projectnav-${projectNavMode}`,
    `chief-${chiefMode}`,
  ].join(" ");

  return (
    <div className={shellClass}>
      <RailNav />

      {projectNavMode !== "hidden" && (
        <aside className="projectnav">
          <div className="projectnav-header">
            <span className="projectnav-title">项目</span>
            {projectNavMode === "expanded" && (
              <NavLink to="/projects" className="projectnav-add" title="管理项目">+</NavLink>
            )}
            <button
              className="projectnav-toggle"
              onClick={cycleProjectNav}
              title={
                projectNavMode === "expanded"
                  ? "折叠为窄栏"
                  : projectNavMode === "compact"
                    ? "完全隐藏"
                    : "展开"
              }
              aria-label="切换项目栏显示"
            >
              {projectNavMode === "expanded" ? "◀" : projectNavMode === "compact" ? "▶" : "≡"}
            </button>
          </div>

          {projectNavMode === "expanded" ? (
            <>
              <ProjectNav />
              {currentProject && (
                <div className="projectnav-footer">
                  <div className="row small">
                    <span className="muted">目标</span>
                    <span className="spacer" />
                    <span className="mono">{formatThousands(currentProject.target_word_count)}字 / {currentProject.target_chapter_count}章</span>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="projectnav-compact-list">
              {projects.map((p) => (
                <button
                  key={p.id}
                  className={`projectnav-compact-item ${p.id === currentProjectId ? "active" : ""}`}
                  onClick={() => selectProject(p.id)}
                  title={`${p.name} · ${p.genre}`}
                  aria-label={p.name}
                >
                  <span className="projectnav-compact-initial">{p.name.slice(0, 1)}</span>
                </button>
              ))}
              {projects.length === 0 && (
                <div className="projectnav-compact-empty muted">+</div>
              )}
            </div>
          )}
        </aside>
      )}

      <main className="main">
        <div className="main-topbar">
          <GlobalSearch />
        </div>
        {children}
      </main>

      {chiefMode !== "hidden" && (
        <ChiefAgentPanel
          projectId={currentProjectId}
          mode={chiefMode}
          pageContext={location.pathname}
          onCycle={cycleChiefPanel}
          onHide={() => setChiefPanelMode("hidden")}
        />
      )}

      {/* R12.2 / P0-UI-7b: floating recovery button shown only when the
          chief panel is fully hidden (and we're on a route where it
          would normally be visible). Mirrors the rail-recover pattern
          already used for projectnav. */}
      {chiefMode === "hidden" && (
        <button
          className="chief-recover-fab"
          onClick={() => setChiefPanelMode("expanded")}
          title="恢复总编面板"
          aria-label="恢复总编面板"
        >
          总
        </button>
      )}

      {/* R16 / P0-UI-8: project nav is hidden by default. Show a
          small affordance so users who want the inline list can
          toggle it on. Mirrors the chief-recover-fab pattern. */}
      {projectNavMode === "hidden" && (
        <button
          className="projectnav-recover-fab"
          onClick={() => setProjectNavMode("expanded")}
          title="展开项目侧边栏"
          aria-label="展开项目侧边栏"
        >
          ☰ 项目
        </button>
      )}

      <BottomStatusBar />
    </div>
  );
}
