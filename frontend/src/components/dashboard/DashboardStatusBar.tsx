/**
 * DashboardStatusBar — Round 3 (P1-UI-5) top status strip.
 *
 * Six slots in a single horizontal row:
 *   [项目] [Worker] [今日字数] [今日成本] [连续失败] [SSE]
 *
 * Designed to live at the very top of the dashboard so the user can
 * tell the system state at a glance without scrolling. Stays compact
 * (one row on >900px viewports; wraps on smaller).
 */
import { Link } from "react-router-dom";
import { useProjectStore } from "../../stores/projectStore";
import { useWorkerStore } from "../../stores/workerStore";
import { useEventStore } from "../../stores/eventStore";
import { getDefaultPolicy } from "../../api";
import type { WorkerPolicy } from "../../types";
import { useEffect, useState } from "react";
import "./DashboardStatusBar.css";

type Props = {
  /** When true, the user hasn't picked a project yet — show a hint. */
  noProject?: boolean;
};

export function DashboardStatusBar({ noProject }: Props) {
  const projects = useProjectStore((s) => s.projects);
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const status = useWorkerStore((s) => s.status);
  const connected = useEventStore((s) => s.connected);
  const [policy, setPolicy] = useState<WorkerPolicy | null>(null);
  const currentProject = projects.find((p) => p.id === currentProjectId);

  useEffect(() => {
    if (currentProjectId) {
      getDefaultPolicy().then(setPolicy).catch(() => setPolicy(null));
    } else {
      setPolicy(null);
    }
  }, [currentProjectId]);

  const todayWords = status?.today_words ?? 0;
  const todayCost = status?.today_cost_usd ?? 0;
  const dailyTarget = policy?.daily_word_goal ?? 30000;
  const dailyBudget = policy?.daily_budget_usd ?? 8;
  const wordPct = Math.min(100, (todayWords / Math.max(1, dailyTarget)) * 100);
  const costPct = Math.min(100, (todayCost / Math.max(0.01, dailyBudget)) * 100);
  const costWarn = costPct >= 80;
  const failures = status?.consecutive_failures ?? 0;
  const workerState = status?.state ?? "idle";
  const workerDotClass = stateColor(workerState);

  return (
    <div className="status-bar-grid">
      <Slot
        label="项目"
        value={
          currentProject ? (
            <Link to={`/projects/${currentProject.id}`} className="status-bar-link gold">
              {currentProject.name}
            </Link>
          ) : (
            <span className="muted">{noProject ? "未选择" : "—"}</span>
          )
        }
        sub={currentProject ? currentProject.genre : ""}
      />
      <Slot
        label="Worker"
        value={
          <span className={`status-bar-value ${workerDotClass}`}>
            <span className={`status-dot status-dot-${workerDotClass}`} />
            {workerState}
          </span>
        }
        sub={status?.current_task_id ? `任务 #${status.current_task_id}` : "空闲"}
      />
      <Slot
        label="今日字数"
        value={formatNumber(todayWords)}
        sub={`目标 ${formatNumber(dailyTarget)} · ${Math.round(wordPct)}%`}
        progress={wordPct}
        progressClass={wordPct >= 80 ? "ok" : "gold"}
      />
      <Slot
        label="今日成本"
        value={`$${todayCost.toFixed(3)}`}
        sub={`预算 $${dailyBudget.toFixed(2)} · ${Math.round(costPct)}%`}
        progress={costPct}
        progressClass={costWarn ? "warn" : "gold"}
      />
      <Slot
        label="连续失败"
        value={
          <span className={failures > 0 ? "warn" : "muted"}>
            {failures}
          </span>
        }
        sub={status?.last_error ? `最近：${status.last_error.slice(0, 22)}…` : "无"}
      />
      <Slot
        label="实时"
        value={
          <span className={connected ? "ok" : "muted"}>
            <span className={`status-dot status-dot-${connected ? "ok" : "info"}`} /> {connected ? "SSE" : "离线"}
          </span>
        }
        sub={connected ? "事件流活跃" : "等待连接…"}
      />
    </div>
  );
}

function Slot({
  label, value, sub, progress, progressClass,
}: {
  label: string;
  value: React.ReactNode;
  sub?: string;
  progress?: number;
  progressClass?: "gold" | "ok" | "warn";
}) {
  return (
    <div className="status-bar-slot">
      <div className="status-bar-label">{label}</div>
      <div className="status-bar-value">{value}</div>
      {sub && <div className="status-bar-sub muted small">{sub}</div>}
      {progress !== undefined && (
        <div className="status-bar-progress">
          <div
            className={`status-bar-progress-fill ${progressClass ?? "gold"}`}
            style={{ width: `${progress}%` }}
          />
        </div>
      )}
    </div>
  );
}

function stateColor(s: string): "ok" | "warn" | "error" | "info" {
  if (s === "running") return "ok";
  if (s === "paused" || s === "paused_budget") return "warn";
  if (s === "error" || s === "stopped") return "error";
  return "info";
}

function formatNumber(n: number): string {
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`;
  return n.toLocaleString();
}
