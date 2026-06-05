type Props = {
  failures: any[];
  loading: boolean;
};

const TYPE_COLORS: Record<string, string> = {
  timeout: "#e0994a",
  auth_error: "#e05555",
  rate_limited: "#d4a85a",
  json_parse_failed: "#9b6fbf",
  empty_response: "#888",
  connection_error: "#e05555",
};

function barColor(type: string): string {
  return TYPE_COLORS[type] ?? "#4a90d9";
}

export function FailureReasonChart({ failures, loading }: Props) {
  if (loading) {
    return <div className="muted small" style={{ padding: 12 }}>加载中…</div>;
  }

  if (!failures.length) {
    return <div className="muted small" style={{ padding: 12 }}>暂无失败数据</div>;
  }

  // 按 failure_type 分组计数
  const counts: Record<string, number> = {};
  failures.forEach((ev: any) => {
    const t = ev.failure_type ?? ev.error_type ?? "other";
    counts[t] = (counts[t] || 0) + 1;
  });

  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const max = entries[0]?.[1] ?? 1;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {entries.map(([type, count]) => (
        <div key={type} style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, color: "var(--muted)", minWidth: 110, textAlign: "right" }}>
            {type}
          </span>
          <div style={{ flex: 1, height: 16, background: "var(--bg-elevated, #1e1e1e)", borderRadius: 3, overflow: "hidden" }}>
            <div style={{
              height: "100%",
              width: `${(count / max) * 100}%`,
              background: barColor(type),
              borderRadius: 3,
              minWidth: 4,
              transition: "width 0.3s",
            }} />
          </div>
          <span style={{ fontSize: 12, fontWeight: 600, minWidth: 32, color: barColor(type) }}>
            {count}
          </span>
        </div>
      ))}
    </div>
  );
}
