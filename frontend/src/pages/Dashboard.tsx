/**
 * Round 3 dashboard — "创作总控台" (Creative Director Console).
 *
 * Refactored out of the round-1 / round-2 monolith into a 6-piece
 * composition so each concern is testable and swappable:
 *
 *   ┌─ DashboardStatusBar ────────────────────────────────────┐
 *   │   project / worker / words / cost / failures / sse      │
 *   └────────────────────────────────────────────────────────┘
 *   ┌─ CurrentPipelinePanel ─────┬─ FailureDiagnosisCard ────┐
 *   │  active task                │  most-recent failure +    │
 *   │  AgentStepRail              │  actionable suggestions   │
 *   │  next actions               │                           │
 *   └─────────────────────────────┴───────────────────────────┘
 *   ┌─ ChapterPreviewCard ────────┬─ UsefulEventStream ───────┐
 *   │  current chapter text       │  filtered live events     │
 *   └─────────────────────────────┴───────────────────────────┘
 *
 * Round-1 deliverables that survive in this layout:
 *   - P1-UI-6 (heartbeat filter) — UsefulEventStream + eventStore
 *   - P1-UI-7 (readable error display) — FailureDiagnosisCard
 *   - the round-1 KPI cards have been replaced by the status bar's
 *     project/worker/words/cost slots; KPI cards are now redundant
 *     with the status bar so we drop them.
 */
import { useEffect, useMemo, useState } from "react";
import { useProjectStore } from "../stores/projectStore";
import { listTasks } from "../api";
import type { AgentTask } from "../types";
import { DashboardStatusBar } from "../components/dashboard/DashboardStatusBar";
import { CurrentPipelinePanel } from "../components/dashboard/CurrentPipelinePanel";
import { FailureDiagnosisCard } from "../components/dashboard/FailureDiagnosisCard";
import { ChapterPreviewCard } from "../components/dashboard/ChapterPreviewCard";
import { UsefulEventStream } from "../components/dashboard/UsefulEventStream";
import { PassFailRateCard } from "../components/dashboard/PassFailRateCard";
import "./Dashboard.css";

export function Dashboard() {
  const projects = useProjectStore((s) => s.projects);
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const [tasks, setTasks] = useState<AgentTask[]>([]);

  useEffect(() => {
    listTasks({ limit: 12 }).then(setTasks).catch(() => {});
    const id = window.setInterval(() => {
      listTasks({ limit: 12 }).then(setTasks).catch(() => {});
    }, 4000);
    return () => window.clearInterval(id);
  }, []);

  const currentProject = projects.find((p) => p.id === currentProjectId);
  const noProject = !currentProject;
  // P1-UI-7: most recent failed task in the top-12 list drives the
  // FailureDiagnosisCard. We pick a *different* task than the one
  // the CurrentPipelinePanel is showing so the user can see both:
  //   - The pipeline panel surfaces the currently-running task.
  //   - The diagnosis card surfaces the most-recent failure even if
  //     a new task has since started.
  const latestFailed = useMemo(
    () => tasks.find((t) => t.status === "failed" || t.status === "cancelled") ?? null,
    [tasks],
  );

  return (
    <div className="dashboard">
      <header className="page-header">
        <div>
          <h1 className="page-title">工作台</h1>
          <p className="page-subtitle">
            {currentProject
              ? `当前项目：${currentProject.name} · ${currentProject.genre}`
              : "还没有选择项目 — 左侧项目栏选一个，或新建一个开始。"}
          </p>
        </div>
      </header>

      <div className="dashboard-body">
        <DashboardStatusBar noProject={noProject} />

        <div className="dashboard-row">
          <CurrentPipelinePanel />
          {latestFailed && (
            <section className="card dashboard-failure-wrap">
              <div className="card-header">
                <h3>最近失败诊断</h3>
                <span className="muted small">任务 #{latestFailed.id} · {latestFailed.status}</span>
              </div>
              <div className="dashboard-failure-body">
                <FailureDiagnosisCard
                  task={latestFailed}
                  onChanged={() => listTasks({ limit: 12 }).then(setTasks).catch(() => {})}
                />
              </div>
            </section>
          )}
        </div>

        <div className="dashboard-row dashboard-row-full">
          <PassFailRateCard projectId={currentProjectId} />
        </div>

        <div className="dashboard-row">
          <ChapterPreviewCard />
          <UsefulEventStream />
        </div>
      </div>
    </div>
  );
}
