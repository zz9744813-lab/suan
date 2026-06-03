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
  const cycleProjectNav = useLayoutStore((s) => s.cycleProjectNav);
  const cycleChiefPanel = useLayoutStore((s) => s.cycleChiefPanel);

  const location = useLocation();
  const chiefIsForced = !location.pathname.startsWith("/dashboard")
    && !location.pathname.startsWith("/projects");
  // The chief panel is route-gated: on /tasks, /worker, /models,
  // /prompts, /study we hide it entirely. On /dashboard and /projects
  // it follows the user's mode choice.
  const chiefMode = chiefIsForced ? "hidden" : chiefPanelMode;

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
          onCycle={cycleChiefPanel}
        />
      )}

      <BottomStatusBar />
    </div>
  );
}
