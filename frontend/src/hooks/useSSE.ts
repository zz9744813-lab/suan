import { useEffect } from "react";
import { apiBase } from "../api/client";
import { useEventStore, type LiveEvent } from "../stores/eventStore";

// Connects to the backend SSE stream and pushes events into the store.
// Reconnects on disconnect with a small backoff.
export function useSSE() {
  const push = useEventStore((s) => s.push);
  const setConnected = useEventStore((s) => s.setConnected);

  useEffect(() => {
    let es: EventSource | null = null;
    let cancelled = false;
    let backoff = 1000;

    function connect() {
      if (cancelled) return;
      es = new EventSource(`${apiBase}/api/events/stream`);
      es.onopen = () => {
        setConnected(true);
        backoff = 1000;
      };
      es.onerror = () => {
        setConnected(false);
        es?.close();
        if (!cancelled) {
          setTimeout(connect, backoff);
          backoff = Math.min(backoff * 2, 8000);
        }
      };
      // Listen to a small set of named event types. Unknown types still fall
      // through the default `message` handler.
      const names = [
        "app.ready", "worker.started", "worker.paused", "worker.resumed",
        "worker.stopped", "worker.loop_crashed", "worker.stale_tasks_recovered",
        "task.failed", "task.succeeded",
        "pipeline.started", "pipeline.completed",
        "reader_review.completed", "comment_triage.completed",
        "comment_discussion.completed", "comment_cleanup.completed",
        "detail_guard.hard_conflict", "sse.connected", "sse.heartbeat",
      ];
      for (const n of names) {
        es.addEventListener(n, (e: MessageEvent) => {
          try {
            const data = JSON.parse(e.data);
            push({
              id: 0,
              event_type: n,
              level: data.level ?? "info",
              message: data.message ?? "",
              project_id: data.project_id ?? null,
              chapter_id: data.chapter_id ?? null,
              task_id: data.task_id ?? null,
              ts: data.ts ?? Date.now() / 1000,
              data,
            } as LiveEvent);
          } catch (err) {
            // ignore malformed frame
          }
        });
      }
      // Generic onmessage catches anything we didn't subscribe to by name.
      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          push({
            id: 0,
            event_type: data.event_type ?? "message",
            level: "info",
            message: data.message ?? JSON.stringify(data).slice(0, 200),
            project_id: data.project_id ?? null,
            chapter_id: data.chapter_id ?? null,
            task_id: data.task_id ?? null,
            ts: data.ts ?? Date.now() / 1000,
            data,
          });
        } catch (err) {
          /* ignore */
        }
      };
    }

    connect();
    return () => {
      cancelled = true;
      setConnected(false);
      es?.close();
    };
  }, [push, setConnected]);
}
