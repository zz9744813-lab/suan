type Props = {
  events: any[];
  loading: boolean;
};

function formatTime(iso: string): string {
  try { return new Date(iso).toLocaleTimeString("zh-CN", { hour12: false }); }
  catch { return iso; }
}

export function FallbackTimeline({ events, loading }: Props) {
  if (loading) {
    return <div className="muted small" style={{ padding: 12 }}>加载中…</div>;
  }

  if (!events.length) {
    return <div className="muted small" style={{ padding: 12 }}>暂无 Fallback 记录</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0, position: "relative", paddingLeft: 20 }}>
      {/* 竖线 */}
      <div style={{
        position: "absolute",
        left: 8,
        top: 8,
        bottom: 8,
        width: 2,
        background: "var(--line)",
        borderRadius: 1,
      }} />

      {events.map((ev: any, i: number) => {
        const success = ev.fallback_result === "success" || ev.status === "success";
        const dotColor = success ? "var(--state-ok, #4caf50)" : "var(--danger, #e05555)";

        return (
          <div
            key={ev.id ?? i}
            style={{
              position: "relative",
              paddingLeft: 20,
              paddingBottom: 12,
              fontSize: 12,
            }}
          >
            {/* 圆点 */}
            <div style={{
              position: "absolute",
              left: -16,
              top: 4,
              width: 10,
              height: 10,
              borderRadius: "50%",
              background: dotColor,
              border: "2px solid var(--card, #1a1a1a)",
            }} />

            {/* 时间 + Agent */}
            <div style={{ marginBottom: 2 }}>
              <span style={{ color: "var(--muted)", fontSize: 11, marginRight: 8 }}>
                {formatTime(ev.created_at)}
              </span>
              <span style={{ fontWeight: 600 }}>{ev.agent_role_key ?? "—"}</span>
            </div>

            {/* 从 → 到 */}
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 2 }}>
              <span style={{ color: "var(--danger, #e05555)" }}>
                {ev.fallback_from ?? `${ev.provider_name ?? "?"}/${ev.model_name ?? "?"}`}
              </span>
              {" → "}
              <span style={{ color: "var(--state-ok, #4caf50)" }}>
                {ev.fallback_to ?? `${ev.fallback_provider ?? "?"}/${ev.fallback_model ?? "?"}`}
              </span>
            </div>

            {/* 原因 + 结果 */}
            <div style={{ fontSize: 11, color: "var(--muted)" }}>
              {ev.fallback_reason ?? ev.error_type ?? "—"}
              {" · "}
              <span style={{ color: dotColor }}>
                {success ? "成功" : "失败"}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
