type Props = {
  providers: any[];
  loading: boolean;
  onExpand: (providerId: number) => void;
  expandedId: number | null;
  modelStats: any[];
};

function statusDot(status: string): string {
  switch (status) {
    case "healthy": return "var(--state-ok, #4caf50)";
    case "degraded": return "var(--warning, #d4a85a)";
    case "down": return "var(--danger, #e05555)";
    default: return "var(--muted, #888)";
  }
}

function rateColor(rate: number): string {
  if (rate < 0.8) return "var(--danger, #e05555)";
  if (rate < 0.95) return "var(--warning, #d4a85a)";
  return "var(--state-ok, #4caf50)";
}

export function ProviderHealthTable({ providers, loading, onExpand, expandedId, modelStats }: Props) {
  if (loading) {
    return <div className="muted small" style={{ padding: 12 }}>加载中…</div>;
  }

  if (!providers.length) {
    return <div className="muted small" style={{ padding: 12 }}>暂无 Provider 数据</div>;
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table className="table" style={{ fontSize: 12 }}>
        <thead>
          <tr>
            <th style={{ width: 24 }}></th>
            <th>Provider</th>
            <th>调用</th>
            <th>成功率</th>
            <th>失败</th>
            <th>超时</th>
            <th>Fallback</th>
            <th>平均延迟</th>
            <th>P95</th>
            <th>Token</th>
            <th>成本</th>
            <th>最近错误</th>
          </tr>
        </thead>
        <tbody>
          {providers.map((p: any) => {
            const pid = p.provider_id ?? p.id;
            const expanded = expandedId === pid;
            const sr = p.success_rate ?? 0;
            return (
              <tr key={pid} style={{ cursor: "pointer" }} onClick={() => onExpand(expanded ? -1 : pid)}>
                <td>
                  <span style={{
                    display: "inline-block", width: 8, height: 8, borderRadius: "50%",
                    background: statusDot(p.health_status ?? "unknown"),
                  }} />
                </td>
                <td style={{ fontWeight: 600 }}>{p.provider_name ?? p.name}</td>
                <td>{p.call_count ?? "—"}</td>
                <td style={{ color: rateColor(sr) }}>
                  {sr != null ? `${(sr * 100).toFixed(0)}%` : "—"}
                </td>
                <td>{p.failed_count ?? "—"}</td>
                <td>{p.timeout_count ?? "—"}</td>
                <td>{p.fallback_count ?? "—"}</td>
                <td>{p.avg_latency_ms != null ? `${Math.round(p.avg_latency_ms)}ms` : "—"}</td>
                <td>{p.p95_latency_ms != null ? `${Math.round(p.p95_latency_ms)}ms` : "—"}</td>
                <td>{p.total_tokens != null ? p.total_tokens.toLocaleString() : "—"}</td>
                <td>{p.cost_usd != null ? `$${p.cost_usd.toFixed(2)}` : "—"}</td>
                <td className="muted small" style={{ maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {p.last_error ?? "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
        {expandedId != null && modelStats.length > 0 && (
          <tbody>
            <tr>
              <td colSpan={12} style={{ padding: 0, background: "var(--bg-elevated)" }}>
                <div style={{ padding: "8px 16px" }}>
                  <div className="muted small" style={{ marginBottom: 6 }}>模型列表</div>
                  <table className="table" style={{ fontSize: 11 }}>
                    <thead>
                      <tr>
                        <th>模型</th>
                        <th>调用</th>
                        <th>成功率</th>
                        <th>平均延迟</th>
                        <th>Token</th>
                        <th>成本</th>
                      </tr>
                    </thead>
                    <tbody>
                      {modelStats.map((m: any, i: number) => (
                        <tr key={i}>
                          <td>{m.model_name}</td>
                          <td>{m.call_count ?? "—"}</td>
                          <td style={{ color: rateColor(m.success_rate ?? 0) }}>
                            {m.success_rate != null ? `${(m.success_rate * 100).toFixed(0)}%` : "—"}
                          </td>
                          <td>{m.avg_latency_ms != null ? `${Math.round(m.avg_latency_ms)}ms` : "—"}</td>
                          <td>{m.total_tokens != null ? m.total_tokens.toLocaleString() : "—"}</td>
                          <td>{m.cost_usd != null ? `$${m.cost_usd.toFixed(3)}` : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </td>
            </tr>
          </tbody>
        )}
      </table>
    </div>
  );
}
