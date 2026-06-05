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
import { listTasks, multiWorkerStatus } from "../api";
import type { AgentTask, MultiWorkerStatus } from "../types";
import { DashboardStatusBar } from "../components/dashboard/DashboardStatusBar";
import { CurrentPipelinePanel } from "../components/dashboard/CurrentPipelinePanel";
import { FailureDiagnosisCard } from "../components/dashboard/FailureDiagnosisCard";
import { ChapterPreviewCard } from "../components/dashboard/ChapterPreviewCard";
import { UsefulEventStream } from "../components/dashboard/UsefulEventStream";
import { PassFailRateCard } from "../components/dashboard/PassFailRateCard";
import { DashboardKpiCards } from "../components/dashboard/DashboardKpiCards";
import { AgentPipelineVisualization } from "../components/dashboard/AgentPipelineVisualization";
import { MemoryLayerCard } from "../components/dashboard/MemoryLayerCard";
import { ReaderFeedbackPanel } from "../components/dashboard/ReaderFeedbackPanel";
import { DiscussionLoopCard } from "../components/dashboard/DiscussionLoopCard";
import { SkillGeneratedCard } from "../components/dashboard/SkillGeneratedCard";
import "./Dashboard.css";

export function Dashboard() {
  const projects = useProjectStore((s) => s.projects);
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [multiStatus, setMultiStatus] = useState<MultiWorkerStatus | null>(null);

  useEffect(() => {
    listTasks({ limit: 12 }).then(setTasks).catch(() => {});
    multiWorkerStatus().then(setMultiStatus).catch(() => {});
    const id = window.setInterval(() => {
      listTasks({ limit: 12 }).then(setTasks).catch(() => {});
      multiWorkerStatus().then(setMultiStatus).catch(() => {});
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
      <div className="dashboard-body">
        <DashboardKpiCards projectId={currentProjectId} />
        <AgentPipelineVisualization />
        <MemoryLayerCard />
        <DashboardStatusBar noProject={noProject} />

        {/* B3: per-domain worker horizontal scaling status */}
        {multiStatus && <DomainWorkersCompact ms={multiStatus} />}

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

        {/* NF2 闭环: Reader 反馈 + 讨论留痕 */}
        <div className="dashboard-row">
          <ReaderFeedbackPanel />
          <DiscussionLoopCard />
        </div>

        {/* NF2 闭环: 沉淀技能 */}
        <div className="dashboard-row dashboard-row-full">
          <SkillGeneratedCard />
        </div>
      </div>
    </div>
  );
}

/** B3: compact per-domain worker status bar.
 *
 * Renders a single-row strip showing each domain partition's
 * running/idle state: ● = running, ○ = idle.
 */
function DomainWorkersCompact({ ms }: { ms: MultiWorkerStatus }) {
  const entries: { key: string; label: string; running: boolean }[] = [
    { key: "writing_worker",  label: "写作",  running: ms.writing_worker.status === "running" },
    { key: "deepstudy_worker", label: "研读",  running: ms.deepstudy_worker.status === "running" },
    { key: "discussion_worker", label: "讨论", running: ms.discussion_worker.status === "running" },
    { key: "memory_worker",  label: "记忆",  running: ms.memory_worker.status === "running" },
    { key: "model_router",   label: "模型",  running: ms.model_router.status === "healthy" },
  ];

  return (
    <div style={{
      display: "flex",
      gap: "1rem",
      alignItems: "center",
      padding: "6px 12px",
      fontSize: "13px",
      fontFamily: "monospace",
      color: "var(--color-text-secondary, #888)",
      borderBottom: "1px solid var(--color-border, #333)",
    }}>
      {entries.map((e) => (
        <span key={e.key} style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{
            display: "inline-block",
            width: 10,
            height: 10,
            borderRadius: "50%",
            background: e.running ? "#4caf50" : "#555",
            boxShadow: e.running ? "0 0 4px #4caf50" : "none",
          }} />
          <span style={{ color: e.running ? "var(--color-text, #ddd)" : "var(--color-text-secondary, #666)" }}>
            {e.label}
          </span>
        </span>
      ))}
    </div>
  );
}
