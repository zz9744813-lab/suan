type Props = {
  events: any[];
  loading: boolean;
};

function latencyColor(ms: number): string {
  if (ms > 30000) return "var(--danger, #e05555)";
  if (ms > 10000) return "#e0994a";
  if (ms > 5000) return "var(--warning, #d4a85a)";
  return "var(--text-secondary)";
}

function formatTime(iso: string): string {
  try { return new Date(iso).toLocaleTimeString("zh-CN", { hour12: false }); }
  catch { return iso; }
}

export function SlowRequestList({ events, loading }: Props) {
  if (loading) {
    return <div className="muted small" style={{ padding: 12 }}>加载中…</div>;
  }

  if (!events.length) {
    return <div className="muted small" style={{ padding: 12 }}>暂无慢请求</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {events.map((ev: any, i: number) => {
        const ms = ev.latency_ms ?? 0;
        return (
          <div
            key={ev.id ?? i}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: "6px 8px",
              fontSize: 12,
              borderBottom: "1px solid var(--line)",
            }}
          >
            <span style={{ color: "var(--muted)", fontSize: 11, minWidth: 70 }}>
              {formatTime(ev.created_at)}
            </span>
            <span style={{ fontWeight: 600, minWidth: 80 }}>
              {ev.agent_role_key ?? "—"}
            </span>
            <span style={{ color: "var(--muted)", fontSize: 11, minWidth: 140 }}>
              {ev.provider_name ?? "—"}/{ev.model_name ?? "—"}
            </span>
            <span style={{ fontWeight: 700, color: latencyColor(ms), minWidth: 80, textAlign: "right" }}>
              {ms.toLocaleString()}ms
            </span>
            <span className="pill" style={{
              fontSize: 10,
              color: ev.status === "success" ? "var(--state-ok, #4caf50)" : "var(--danger, #e05555)",
            }}>
              {ev.status === "success" ? "成功" : ev.status ?? "—"}
            </span>
          </div>
        );
      })}
    </div>
  );
}
