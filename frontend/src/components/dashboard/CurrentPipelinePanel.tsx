/**
 * CurrentPipelinePanel — Round 3 (P1-UI-5).
 *
 * The left half of the dashboard's top row. Shows whichever task is
 * currently in motion:
 *   - chapter_pipeline currently running
 *   - or the most recent task if Worker is idle
 *   - or a "Worker 空闲" empty state with quick-start buttons
 *
 * Renders the AgentStepRail inside, plus a "下一步动作" footer
 * that changes depending on the task's status (running / failed /
 * succeeded).
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useProjectStore } from "../../stores/projectStore";
import { useWorkerStore } from "../../stores/workerStore";
import { useEventStore } from "../../stores/eventStore";
import {
  listTasks, getTask, workerStart, workerPause, workerResume, workerStop,
  cancelTask, createTask, getTaskDiagnosis, type RetryMode,
} from "../../api";
import type { AgentTask, TaskDiagnosis, Chapter } from "../../types";
import { AgentStepRail } from "./AgentStepRail";
import "./CurrentPipelinePanel.css";

export function CurrentPipelinePanel() {
  const projects = useProjectStore((s) => s.projects);
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const workerState = useWorkerStore((s) => s.status?.state ?? "idle");
  const refreshWorker = useWorkerStore((s) => s.refresh);
  const [task, setTask] = useState<AgentTask | null>(null);
  const [diagnosis, setDiagnosis] = useState<TaskDiagnosis | null>(null);
  const [nextChapter, setNextChapter] = useState<Chapter | null>(null);
  const [busy, setBusy] = useState(false);

  const currentProject = projects.find((p) => p.id === currentProjectId);

  // Refresh every 4s. We only keep one "current" task in state — the
  // running one if any, else the most recent task in the project.
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      if (!currentProjectId) { setTask(null); setDiagnosis(null); return; }
      try {
        const tasks = await listTasks({ project_id: currentProjectId, limit: 1 });
        const t = tasks[0] ?? null;
        if (cancelled) return;
        setTask(t);
        if (t && (t.status === "failed" || t.status === "cancelled")) {
          const d = await getTaskDiagnosis(t.id);
          if (!cancelled) setDiagnosis(d);
        } else {
          setDiagnosis(null);
        }
      } catch { /* swallow */ }
    };
    tick();
    const id = window.setInterval(tick, 4000);
    return () => { cancelled = true; window.clearInterval(id); };
  }, [currentProjectId]);

  // Worker controls
  const onStartWorker = async () => {
    setBusy(true);
    try { await workerStart(); refreshWorker(); } finally { setBusy(false); }
  };
  const onPauseWorker = async () => {
    setBusy(true);
    try { await workerPause(); refreshWorker(); } finally { setBusy(false); }
  };
  const onResumeWorker = async () => {
    setBusy(true);
    try { await workerResume(); refreshWorker(); } finally { setBusy(false); }
  };
  const onStopWorker = async () => {
    setBusy(true);
    try { await workerStop(); refreshWorker(); } finally { setBusy(false); }
  };
  const onCancelTask = async () => {
    if (!task) return;
    setBusy(true);
    try { await cancelTask(task.id); } finally { setBusy(false); }
  };

  if (!currentProjectId) {
    return (
      <section className="dashboard-card pipeline-card">
        <div className="card-header">
          <h3>当前生产线</h3>
        </div>
        <div className="pipeline-empty">
          <div className="pipeline-empty-glyph">书</div>
          <p>左侧项目栏选一个项目，然后启动 Worker 开始流水线。</p>
          <Link to="/projects" className="gold">打开项目列表 →</Link>
        </div>
      </section>
    );
  }

  const isFailed = task?.status === "failed" || task?.status === "cancelled";
  const isRunning = task?.status === "running" || task?.status === "pending";
  const isSucceeded = task?.status === "succeeded";

  return (
    <section className="dashboard-card pipeline-card">
      <div className="card-header">
        <h3>当前生产线</h3>
        <div className="card-header-meta">
          {task ? (
            <span className="badge ok">
              <span className={`status-dot status-dot-${stateColor(workerState)}`} />
              {task.status} · 任务 #{task.id}
            </span>
          ) : (
            <span className="muted small">暂无任务</span>
          )}
        </div>
      </div>

      {!task ? (
        <div className="pipeline-empty">
          <p className="muted">当前项目还没有任务。</p>
          <div className="row">
            <Link to={`/projects/${currentProjectId}`} className="button">打开项目</Link>
            {workerState !== "running" && (
              <button className="primary" onClick={onStartWorker} disabled={busy}>启动 Worker</button>
            )}
          </div>
        </div>
      ) : (
        <>
          <div className="pipeline-headline">
            <div>
              <div className="pipeline-headline-row">
                {task.chapter_id ? (
                  <Link to={`/projects/${task.project_id}/chapters/${task.chapter_id}`} className="pipeline-chapter gold">
                    第 {task.chapter_id} 章
                  </Link>
                ) : <span className="muted">—</span>}
                <span className="muted small">· {task.task_type}</span>
              </div>
              <div className="pipeline-headline-row small muted">
                {isFailed && diagnosis?.failed_agent && (
                  <>失败 Agent：<b className="warn">{diagnosis.failed_agent}</b></>
                )}
                {isFailed && !diagnosis?.failed_agent && task.error && (
                  <>错误：{task.error.slice(0, 60)}{task.error.length > 60 ? "…" : ""}</>
                )}
                {isRunning && <>运行中…</>}
                {isSucceeded && <>已完成 · ${task.cost_usd.toFixed(3)} · {(task.input_tokens/1000).toFixed(1)}k tok</>}
              </div>
            </div>
            <div className="pipeline-headline-meta">
              <span className="mono small">${task.cost_usd.toFixed(4)}</span>
            </div>
          </div>

          {diagnosis && diagnosis.steps.length > 0 && (
            <div className="pipeline-rail">
              <AgentStepRail steps={diagnosis.steps} />
            </div>
          )}

          {isFailed && diagnosis?.impact && diagnosis.impact.length > 0 && (
            <div className="pipeline-impact">
              <span className="muted small">影响：</span>
              {diagnosis.impact.map((i, idx) => (
                <span key={idx} className="pipeline-impact-chip">{i}</span>
              ))}
            </div>
          )}

          {/* Next actions — context-aware buttons */}
          <div className="pipeline-actions">
            {isFailed && task.chapter_id && (
              <Link to={`/projects/${task.project_id}/chapters/${task.chapter_id}`} className="button">
                查看 Step
              </Link>
            )}
            {isFailed && (
              <Link to="/models" className="button">打开模型配置</Link>
            )}
            {isRunning && (
              <button className="danger" onClick={onCancelTask} disabled={busy}>取消任务</button>
            )}
            {isSucceeded && task.chapter_id && currentProject && (
              <button
                className="primary"
                onClick={async () => {
                  setBusy(true);
                  try {
                    await createTask({
                      project_id: currentProject.id,
                      chapter_id: task.chapter_id!,
                      task_type: "chapter_pipeline",
                      priority: 100,
                      payload: { mode: "full" },
                    });
                    await workerStart();
                    refreshWorker();
                  } finally { setBusy(false); }
                }}
                disabled={busy || !nextChapter}
              >
                重跑本章节
              </button>
            )}

            <span className="spacer" />

            {/* Worker controls */}
            {workerState === "running" && (
              <>
                <button onClick={onPauseWorker} disabled={busy}>暂停 Worker</button>
                <button className="danger" onClick={onStopWorker} disabled={busy}>停止 Worker</button>
              </>
            )}
            {(workerState === "paused" || workerState === "stopped" || workerState === "idle") && (
              <button className="primary" onClick={onStartWorker} disabled={busy}>启动 Worker</button>
            )}
            {workerState === "paused" && (
              <button onClick={onResumeWorker} disabled={busy}>恢复 Worker</button>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function stateColor(s: string): "ok" | "warn" | "error" | "info" {
  if (s === "running") return "ok";
  if (s === "paused" || s === "paused_budget") return "warn";
  if (s === "error" || s === "stopped") return "error";
  return "info";
}
