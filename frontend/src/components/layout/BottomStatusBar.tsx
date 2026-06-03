/**
 * BottomStatusBar — persistent 28px strip at the bottom of the shell.
 *
 * Shows at a glance:
 *   - Worker dot + state name
 *   - Today words / today cost
 *   - Last error (if any, truncated)
 *   - Current project name
 *
 * The data is read from workerStore / projectStore. We never block
 * the UI on these — a missing status just renders muted text.
 */
import { useProjectStore } from "../../stores/projectStore";
import { useWorkerStore } from "../../stores/workerStore";
import { stateColor } from "../../lib/stateColor";
import { formatThousands } from "../../lib/format";
import "./BottomStatusBar.css";

export function BottomStatusBar() {
  const workerState = useWorkerStore((s) => s.status?.state ?? "idle");
  const todayWords = useWorkerStore((s) => s.status?.today_words ?? 0);
  const todayCost = useWorkerStore((s) => s.status?.today_cost_usd ?? 0);
  const lastError = useWorkerStore((s) => s.status?.last_error ?? null);

  const projects = useProjectStore((s) => s.projects);
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const currentProject = projects.find((p) => p.id === currentProjectId);

  return (
    <footer className="statusbar">
      <span className="statusbar-section">
        <span className={`status-dot status-dot-${stateColor(workerState)}`} />
        <span>Worker:&nbsp;<b>{workerState}</b></span>
      </span>

      <span className="status-sep" />

      <span className="statusbar-section">
        今日 <b className="mono">{formatThousands(todayWords)}</b> 字
      </span>

      <span className="status-sep" />

      <span className="statusbar-section">
        今日成本 <b className="mono">${todayCost.toFixed(3)}</b>
      </span>

      {lastError && (
        <>
          <span className="status-sep" />
          <span className="statusbar-section statusbar-error ellipsis" title={lastError}>
            最近错误:{lastError.slice(0, 60)}
          </span>
        </>
      )}

      <span className="spacer" />

      <span className="statusbar-section statusbar-project">
        {currentProject ? (
          <>当前项目:&nbsp;<b>{currentProject.name}</b></>
        ) : (
          <span className="muted">未选择项目</span>
        )}
      </span>
    </footer>
  );
}
