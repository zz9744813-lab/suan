/**
 * UsefulEventStream — Round 3 (P1-UI-5 / P1-UI-6).
 *
 * Real-time event timeline. The eventStore already drops
 * sse.heartbeat / sse.connected / app.ready; this component adds
 * a second filter to keep only events that are useful in the
 * dashboard context (task / agent / pipeline / error / worker).
 * Anything else is hidden.
 */
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
];

function isUseful(e: LiveEvent): boolean {
  // Drop everything that doesn't start with a useful prefix. The
  // backend's event_type space is small and curated; if we don't
  // know the prefix it's likely noise (e.g. debug / sse.keepalive).
  return USEFUL_PREFIXES.some((p) => e.event_type.startsWith(p));
}

export function UsefulEventStream() {
  const events = useEventStore((s) => s.events);
  const filtered = events.filter(isUseful).slice(-30).reverse();
  return (
    <section className="card event-card">
      <div className="card-header">
        <h3>实时事件</h3>
        <span className="muted small">最近 {filtered.length} 条</span>
      </div>
      <div className="event-feed">
        {filtered.length === 0 ? (
          <div className="event-empty muted small">等待事件…</div>
        ) : (
          filtered.map((e) => (
            <div key={e.id} className={`event-row event-${e.level}`}>
              <span className="event-time mono tiny">
                {new Date(e.ts * 1000).toLocaleTimeString("zh-CN", {
                  hour: "2-digit", minute: "2-digit", second: "2-digit",
                })}
              </span>
              <span className={`badge event-type event-type-${e.level}`}>{e.event_type}</span>
              <span className="event-msg ellipsis">{e.message}</span>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
