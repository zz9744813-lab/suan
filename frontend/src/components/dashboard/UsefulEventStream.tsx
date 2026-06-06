import { useEventStore } from "../../stores/eventStore";
import type { LiveEvent } from "../../stores/eventStore";
import "./UsefulEventStream.css";

const USEFUL_PREFIXES = [
  "task.",
  "agent.",
  "pipeline.",
  "error.",
  "worker.",
  "study.",
  "behavior.",
  "graph.",
  "chief.",
  "discussion.",
  "model.",
  "models.",
];

function isUseful(e: LiveEvent): boolean {
  return USEFUL_PREFIXES.some((p) => e.event_type.startsWith(p));
}

type EventBucket = "errors" | "production" | "agents" | "models";

const BUCKETS: { key: EventBucket; label: string; hint: string }[] = [
  { key: "errors", label: "错误", hint: "需要处理" },
  { key: "production", label: "生产", hint: "章节 / 拆书 / 图谱" },
  { key: "agents", label: "Agent", hint: "协作与讨论" },
  { key: "models", label: "模型", hint: "调用 / 健康" },
];

function bucketOf(e: LiveEvent): EventBucket {
  if (e.level === "error" || e.event_type.startsWith("error.")) return "errors";
  if (e.event_type.startsWith("model.") || e.event_type.startsWith("models.")) return "models";
  if (e.event_type.startsWith("agent.") || e.event_type.startsWith("chief.") || e.event_type.startsWith("discussion.")) return "agents";
  return "production";
}

function shortType(type: string) {
  const parts = type.split(".");
  return parts.length > 1 ? parts.slice(-2).join(".") : type;
}

export function UsefulEventStream() {
  const events = useEventStore((s) => s.events);
  const filtered = events.filter(isUseful).slice(-80).reverse();
  const grouped = BUCKETS.map((bucket) => {
    const rows = filtered.filter((e) => bucketOf(e) === bucket.key);
    return { ...bucket, rows, latest: rows[0] ?? null };
  });
  const recent = filtered.slice(0, 8);

  return (
    <section className="card event-card">
      <div className="card-header">
        <h3>事件看板</h3>
        <span className="muted small">最近 {filtered.length} 条有效事件</span>
      </div>

      <div className="event-board">
        {grouped.map((bucket) => (
          <div key={bucket.key} className={`event-bucket event-bucket-${bucket.key}`}>
            <div className="event-bucket-top">
              <span>{bucket.label}</span>
              <b>{bucket.rows.length}</b>
            </div>
            <div className="event-bucket-hint">{bucket.hint}</div>
            {bucket.latest ? (
              <div className={`event-bucket-latest event-${bucket.latest.level}`}>
                <span className="mono tiny">{shortType(bucket.latest.event_type)}</span>
                <span className="ellipsis">{bucket.latest.message}</span>
              </div>
            ) : (
              <div className="event-bucket-empty">暂无</div>
            )}
          </div>
        ))}
      </div>

      <div className="event-feed event-feed-board">
        {recent.length === 0 ? (
          <div className="event-empty muted small">等待事件...</div>
        ) : (
          recent.map((e) => (
            <div key={e.id} className={`event-row event-${e.level}`}>
              <span className="event-time mono tiny">
                {new Date(e.ts * 1000).toLocaleTimeString("zh-CN", {
                  hour: "2-digit", minute: "2-digit", second: "2-digit",
                })}
              </span>
              <span className={`badge event-type event-type-${e.level}`}>{shortType(e.event_type)}</span>
              <span className="event-msg ellipsis">{e.message}</span>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
