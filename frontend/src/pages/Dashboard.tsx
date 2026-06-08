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
import { Link } from "react-router-dom";
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
import { Skeleton } from "../components/ui/Skeleton";
import { EmptyState } from "../components/ui/EmptyState";
import "./Dashboard.css";

export function Dashboard() {
  const projects = useProjectStore((s) => s.projects);
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const [loading, setLoading] = useState(true);
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [multiStatus, setMultiStatus] = useState<MultiWorkerStatus | null>(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      listTasks({ limit: 12 }).then(setTasks).catch(() => {}),
      multiWorkerStatus().then(setMultiStatus).catch(() => {}),
    ]).finally(() => setLoading(false));

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
  const taskStats = useMemo(() => {
    return {
      pending: tasks.filter((t) => t.status === "pending").length,
      running: tasks.filter((t) => t.status === "running").length,
      failed: tasks.filter((t) => t.status === "failed" || t.status === "cancelled").length,
      deepstudy: tasks.filter((t) => t.domain === "deepstudy").length,
      cost: tasks.reduce((sum, t) => sum + (t.cost_usd ?? 0), 0),
    };
  }, [tasks]);

  return (
    <div className="dashboard">
      <div className="dashboard-body">
        <DashboardStatusBar noProject={noProject} />

        {loading ? (
          <>
            <div style={{ height: 48, marginBottom: 16 }}>
              <Skeleton height={48} radius="md" />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <Skeleton height={200} radius="lg" />
              <Skeleton height={200} radius="lg" />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
              <Skeleton height={180} radius="lg" />
              <Skeleton height={180} radius="lg" />
            </div>
          </>
        ) : (
        <>
        {/* B3: per-domain worker horizontal scaling status */}
        {multiStatus && <DomainWorkersCompact ms={multiStatus} />}

        <WorkbenchCommandStrip
          projectName={currentProject?.name ?? null}
          projectId={currentProjectId}
          stats={taskStats}
        />

        <DashboardKpiCards projectId={currentProjectId} />

        <div className="dashboard-row">
          <AgentPipelineVisualization />
          <MemoryLayerCard />
        </div>

        <div className="dashboard-row">
          {tasks.length === 0 ? (
            <EmptyState
              title="暂无流水线任务"
              description="还没有创建任何任务，去创建一个新任务开始创作吧。"
            />
          ) : (
            <CurrentPipelinePanel />
          )}
          {latestFailed && (
            <section className="dashboard-card dashboard-failure-wrap">
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
        </>
        )}
      </div>
    </div>
  );
}

function WorkbenchCommandStrip({
  projectName,
  projectId,
  stats,
}: {
  projectName: string | null;
  projectId: number | null;
  stats: { pending: number; running: number; failed: number; deepstudy: number; cost: number };
}) {
  return (
    <section className="workbench-command">
      <div className="workbench-command-main">
        <div className="workbench-command-kicker">当前工作台</div>
        <div className="workbench-command-title">{projectName ?? "未选择项目"}</div>
        <div className="workbench-command-sub">
          {projectId ? "生产线、拆书、模型和记忆状态集中在这里。" : "先选择一个项目，系统才知道要把产能投到哪里。"}
        </div>
      </div>
      <div className="workbench-command-metrics">
        <Metric label="排队" value={stats.pending} />
        <Metric label="运行" value={stats.running} />
        <Metric label="失败" value={stats.failed} tone={stats.failed > 0 ? "warn" : "ok"} />
        <Metric label="拆书" value={stats.deepstudy} />
        <Metric label="成本" value={`$${stats.cost.toFixed(3)}`} />
      </div>
      <div className="workbench-command-actions">
        {projectId ? (
          <Link to={`/projects/${projectId}`} className="button primary">打开项目</Link>
        ) : (
          <Link to="/projects" className="button primary">选择项目</Link>
        )}
        <Link to="/study/library" className="button">拆书书架</Link>
        <Link to="/models" className="button">模型配置</Link>
        <Link to="/prompts" className="button">提示词配置</Link>
        <Link to="/prompts-matrix" className="button">提示词矩阵</Link>
      </div>
    </section>
  );
}

function Metric({ label, value, tone }: { label: string; value: number | string; tone?: "ok" | "warn" }) {
  return (
    <div className={`workbench-metric ${tone ? `workbench-metric-${tone}` : ""}`}>
      <span>{label}</span>
      <b>{value}</b>
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
    { key: "deepstudy_worker", label: "拆书",  running: ms.deepstudy_worker.status === "running" },
    { key: "discussion_worker", label: "讨论", running: ms.discussion_worker.status === "running" },
    { key: "memory_worker",  label: "记忆",  running: ms.memory_worker.status === "running" },
    { key: "model_router",   label: "模型",  running: ms.model_router.status === "healthy" },
  ];

  return (
    <div className="domain-workers">
      {entries.map((e) => (
        <span key={e.key} className={`domain-worker ${e.running ? "running" : ""}`}>
          <span className="domain-worker-dot" />
          <span>{e.label}</span>
        </span>
      ))}
    </div>
  );
}
