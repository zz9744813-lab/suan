type Summary = {
  total_calls: number;
  success_rate: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  fallback_count: number;
  failed_count: number;
  timeout_count: number;
  cache_hit_rate: number;
};

type Props = {
  summary: Summary | null;
  loading: boolean;
};

function fmt(n: number, suffix = ""): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M" + suffix;
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K" + suffix;
  return n.toFixed(n % 1 === 0 ? 0 : 1) + suffix;
}

function rateColor(rate: number): string {
  if (rate < 0.8) return "var(--danger, #e05555)";
  if (rate < 0.95) return "var(--warning, #d4a85a)";
  return "var(--state-ok, #4caf50)";
}

function costColor(cost: number): string {
  if (cost > 5) return "var(--danger, #e05555)";
  if (cost > 1) return "var(--warning, #d4a85a)";
  return "var(--state-ok, #4caf50)";
}

export function ObservabilityKpiGrid({ summary, loading }: Props) {
  if (loading) {
    return (
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} style={{ padding: 12, borderRadius: 8, background: "var(--card)", border: "1px solid var(--line)" }}>
            <div style={{ fontSize: 11, color: "var(--muted)" }}>—</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: "var(--muted)" }}>…</div>
          </div>
        ))}
      </div>
    );
  }

  const s = summary;
  const sr = s?.success_rate ?? 0;

  const cards: { label: string; value: string; color?: string }[] = [
    { label: "总调用", value: fmt(s?.total_calls ?? 0) },
    { label: "成功率", value: sr != null ? `${(sr * 100).toFixed(1)}%` : "—", color: rateColor(sr) },
    { label: "平均延迟", value: fmt(s?.avg_latency_ms ?? 0, "ms") },
    { label: "P95 延迟", value: fmt(s?.p95_latency_ms ?? 0, "ms") },
    { label: "总 Token", value: fmt(s?.total_tokens ?? 0) },
    { label: "输入/输出", value: `${fmt(s?.input_tokens ?? 0)} / ${fmt(s?.output_tokens ?? 0)}` },
    { label: "今日成本", value: `$${(s?.cost_usd ?? 0).toFixed(2)}`, color: costColor(s?.cost_usd ?? 0) },
    { label: "Fallback 数", value: fmt(s?.fallback_count ?? 0) },
  ];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
      {cards.map((c) => (
        <div
          key={c.label}
          style={{ padding: 12, borderRadius: 8, background: "var(--card)", border: "1px solid var(--line)" }}
        >
          <div style={{ fontSize: 11, color: "var(--muted)" }}>{c.label}</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: c.color ?? "var(--text)" }}>
            {c.value}
          </div>
        </div>
      ))}
    </div>
  );
}
