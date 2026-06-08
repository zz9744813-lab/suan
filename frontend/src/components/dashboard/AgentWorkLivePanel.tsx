import { useEffect, useMemo, useState } from "react";
import { taskEvents, taskSteps } from "../../api";
import type { AgentEvent, AgentStep, AgentTask } from "../../types";
import "./AgentWorkLivePanel.css";

type TimelineItem = {
  id: string;
  ts: string | null;
  kind: "step" | "event";
  agent: string;
  title: string;
  status: string;
  message: string;
  meta: string[];
  details?: string;
  tone: "running" | "ok" | "warn" | "error" | "idle";
};

export function AgentWorkLivePanel({ tasks }: { tasks: AgentTask[] }) {
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const taskOptions = useMemo(() => {
    return [...tasks]
      .sort((a, b) => scoreTask(b) - scoreTask(a))
      .slice(0, 8);
  }, [tasks]);

  const selectedTask = useMemo(
    () => taskOptions.find((t) => t.id === selectedTaskId) ?? taskOptions[0] ?? null,
    [taskOptions, selectedTaskId],
  );

  useEffect(() => {
    if (!selectedTask && selectedTaskId !== null) setSelectedTaskId(null);
    if (selectedTask && selectedTaskId == null) setSelectedTaskId(selectedTask.id);
  }, [selectedTask, selectedTaskId]);

  useEffect(() => {
    if (!selectedTask) {
      setSteps([]);
      setEvents([]);
      return;
    }
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [nextSteps, nextEvents] = await Promise.all([
          taskSteps(selectedTask.id).catch(() => [] as AgentStep[]),
          taskEvents(selectedTask.id).catch(() => [] as AgentEvent[]),
        ]);
        if (cancelled) return;
        setSteps(nextSteps);
        setEvents(nextEvents);
      } catch (e: any) {
        if (!cancelled) setError(e?.message ?? String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    const interval = window.setInterval(load, selectedTask.status === "running" || selectedTask.status === "pending" ? 2500 : 6000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [selectedTask?.id, selectedTask?.status]);

  const timeline = useMemo(() => buildTimeline(steps, events), [steps, events]);

  return (
    <section className="dashboard-card agent-live-card">
      <div className="card-header agent-live-header">
        <div>
          <h3>Agent 工作实况</h3>
          <span className="muted small">像对话一样查看真实步骤、模型调用、输出和错误</span>
        </div>
        {selectedTask && (
          <span className={`agent-live-state agent-live-state-${toneOfStatus(selectedTask.status)}`}>
            #{selectedTask.id} · {selectedTask.task_type} · {selectedTask.status}
          </span>
        )}
      </div>

      {taskOptions.length > 0 && (
        <div className="agent-live-taskbar">
          {taskOptions.map((task) => (
            <button
              key={task.id}
              className={`agent-live-task ${selectedTask?.id === task.id ? "active" : ""}`}
              onClick={() => setSelectedTaskId(task.id)}
            >
              <span>#{task.id}</span>
              <b>{taskLabel(task.task_type)}</b>
              <em>{task.status}</em>
            </button>
          ))}
        </div>
      )}

      {!selectedTask ? (
        <div className="agent-live-empty">暂无任务。启动项目或 Worker 后，这里会显示 Agent 的工作过程。</div>
      ) : error ? (
        <div className="agent-live-empty agent-live-error">读取过程失败：{error}</div>
      ) : timeline.length === 0 ? (
        <div className="agent-live-empty">
          {loading ? "正在读取 Agent 过程…" : "这个任务还没有写入步骤或事件。任务开始执行后会自动出现。"}
        </div>
      ) : (
        <div className="agent-live-feed" aria-live="polite">
          {timeline.map((item) => (
            <article key={item.id} className={`agent-bubble agent-bubble-${item.kind} agent-bubble-${item.tone}`}>
              <div className="agent-avatar">{avatarOf(item.agent, item.kind)}</div>
              <div className="agent-bubble-body">
                <div className="agent-bubble-top">
                  <div>
                    <strong>{item.agent}</strong>
                    <span>{item.title}</span>
                  </div>
                  <time>{item.ts ? formatTime(item.ts) : "—"}</time>
                </div>
                <p>{item.message}</p>
                {item.meta.length > 0 && (
                  <div className="agent-bubble-meta">
                    {item.meta.map((m) => <span key={m}>{m}</span>)}
                  </div>
                )}
                {item.details && <pre>{item.details}</pre>}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function scoreTask(task: AgentTask) {
  const statusScore =
    task.status === "running" ? 1_000_000 :
    task.status === "pending" ? 900_000 :
    task.status === "succeeded" && task.task_type === "chapter_pipeline" ? 850_000 :
    task.status === "succeeded" ? 760_000 :
    task.status === "failed" || task.status === "cancelled" ? 650_000 :
    0;
  return statusScore + task.id;
}

function buildTimeline(steps: AgentStep[], events: AgentEvent[]): TimelineItem[] {
  const stepItems = steps.map(stepToItem);
  const eventItems = events.map(eventToItem);
  return [...stepItems, ...eventItems]
    .sort((a, b) => timeValue(a.ts) - timeValue(b.ts))
    .slice(-60);
}

function stepToItem(step: AgentStep): TimelineItem {
  const output = summarizeStepOutput(step);
  const prompt = preview(step.input_prompt, 260);
  const meta = [
    step.provider_name && step.model_name ? `${step.provider_name} / ${step.model_name}` : step.model_name ?? step.provider_name ?? null,
    step.duration_ms ? `${Math.round(step.duration_ms / 1000)}s` : null,
    step.cost_usd ? `$${step.cost_usd.toFixed(4)}` : null,
    step.input_tokens || step.output_tokens ? `${step.input_tokens}/${step.output_tokens} tokens` : null,
  ].filter(Boolean) as string[];
  return {
    id: `step-${step.id}`,
    ts: step.finished_at ?? step.started_at ?? step.created_at,
    kind: "step",
    agent: step.agent_name || "Agent",
    title: `${step.step_name} · ${step.status}`,
    status: step.status,
    message: step.error_message ? `执行失败：${step.error_message}` : output || prompt || "步骤已记录，但没有输出摘要。",
    meta,
    details: step.error_message ? preview(step.raw_output, 1200) : preview(step.raw_output || step.input_prompt, 900),
    tone: toneOfStatus(step.status),
  };
}

function eventToItem(event: AgentEvent): TimelineItem {
  const meta = [event.event_type, event.level, event.chapter_id ? `章节 #${event.chapter_id}` : null].filter(Boolean) as string[];
  return {
    id: `event-${event.id}`,
    ts: event.created_at,
    kind: "event",
    agent: event.event_type.startsWith("model") ? "模型路由" : event.event_type.startsWith("worker") ? "Worker" : "系统事件",
    title: event.event_type,
    status: event.level,
    message: event.message || "事件已记录",
    meta,
    details: event.data ? preview(JSON.stringify(event.data, null, 2), 1000) : undefined,
    tone: event.level === "error" ? "error" : event.level === "warning" ? "warn" : "idle",
  };
}

function summarizeStepOutput(step: AgentStep) {
  if (step.parsed_output) {
    const fields = ["summary", "text", "content", "decision", "result", "title"];
    for (const field of fields) {
      const value = step.parsed_output[field];
      if (typeof value === "string" && value.trim()) return preview(value, 360);
    }
    return preview(JSON.stringify(step.parsed_output, null, 2), 360);
  }
  return preview(step.raw_output, 360);
}

function preview(value: string | null | undefined, max = 300) {
  if (!value) return "";
  const text = String(value).replace(/\s+/g, " ").trim();
  if (!text) return "";
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function timeValue(ts: string | null) {
  if (!ts) return 0;
  const value = new Date(ts).getTime();
  return Number.isFinite(value) ? value : 0;
}

function formatTime(ts: string) {
  return new Date(ts).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function toneOfStatus(status: string): TimelineItem["tone"] {
  if (status === "succeeded" || status === "completed") return "ok";
  if (status === "running" || status === "pending") return "running";
  if (status === "failed" || status === "cancelled" || status === "error") return "error";
  if (status === "warning") return "warn";
  return "idle";
}

function taskLabel(type: string) {
  const map: Record<string, string> = {
    chapter_pipeline: "写作流水线",
    reader_review: "读者评审",
    project_bootstrap: "项目启动",
    study_bulk: "拆书批处理",
    study: "拆书",
  };
  return map[type] ?? type;
}

function avatarOf(agent: string, kind: TimelineItem["kind"]) {
  if (kind === "event") return "◇";
  if (/critic|review|reader/i.test(agent)) return "评";
  if (/draft|writer/i.test(agent)) return "写";
  if (/plan/i.test(agent)) return "策";
  if (/memory|learn/i.test(agent)) return "记";
  return "A";
}
