/**
 * ModelFailoverTimeline — Failover 时间线组件
 *
 * 展示最近 ModelCallEvent: 时间、provider/model、状态、延迟
 */

const STATUS_STYLES: Record<string, { color: string; label: string }> = {
  success: { color: "#4ade80", label: "成功" },
  failed: { color: "#f87171", label: "失败" },
  fallback_success: { color: "#facc15", label: "Fallback" },
};

interface Props {
  events: any[];
  loading: boolean;
}

export function ModelFailoverTimeline({ events, loading }: Props) {
  if (loading) {
    return <div className="muted small">加载时间线…</div>;
  }
  if (!events || events.length === 0) {
    return <div className="muted small">暂无 Failover 事件</div>;
  }

  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 4 }}>
      {events.slice(0, 30).map((ev, i) => {
        const st = STATUS_STYLES[ev.status ?? ev.event_type] ?? { color: "#999", label: ev.status ?? ev.event_type ?? "?" };
        return (
          <li key={ev.id ?? i} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
            <span className="muted small" style={{ whiteSpace: "nowrap", minWidth: 60 }}>
              {ev.created_at ? new Date(ev.created_at).toLocaleTimeString("zh-CN") : "—"}
            </span>
            <span
              className="pill tiny"
              style={{ background: st.color + "22", color: st.color, borderColor: st.color + "44" }}
            >
              {st.label}
            </span>
            <span className="small" style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {ev.provider_name ?? (ev.provider_id != null ? `#${ev.provider_id}` : "?")} / {ev.model_name ?? "?"}
            </span>
            {ev.latency_ms != null && (
              <span className="muted small">{ev.latency_ms}ms</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
