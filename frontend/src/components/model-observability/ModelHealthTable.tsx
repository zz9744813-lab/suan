type Props = {
  models: any[];
  loading: boolean;
};

function rateColor(rate: number): string {
  if (rate < 0.8) return "var(--danger, #e05555)";
  if (rate < 0.95) return "var(--warning, #d4a85a)";
  return "var(--state-ok, #4caf50)";
}

export function ModelHealthTable({ models, loading }: Props) {
  if (loading) {
    return <div className="muted small" style={{ padding: 12 }}>加载中…</div>;
  }

  if (!models.length) {
    return <div className="muted small" style={{ padding: 12 }}>暂无模型数据</div>;
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table className="table" style={{ fontSize: 12 }}>
        <thead>
          <tr>
            <th>模型名</th>
            <th>Provider</th>
            <th>调用</th>
            <th>成功率</th>
            <th>平均延迟</th>
            <th>质量失败</th>
            <th>成本</th>
            <th>使用 Agent</th>
          </tr>
        </thead>
        <tbody>
          {models.map((m: any, i: number) => {
            const sr = m.success_rate ?? 0;
            return (
              <tr key={i}>
                <td style={{ fontWeight: 700 }}>{m.model_name ?? "—"}</td>
                <td>{m.provider_name ?? "—"}</td>
                <td>{m.call_count ?? "—"}</td>
                <td style={{ color: rateColor(sr) }}>
                  {sr != null ? `${(sr * 100).toFixed(0)}%` : "—"}
                </td>
                <td>{m.avg_latency_ms != null ? `${Math.round(m.avg_latency_ms)}ms` : "—"}</td>
                <td>{m.quality_failure_count ?? m.failed_count ?? "—"}</td>
                <td>{m.cost_usd != null ? `$${m.cost_usd.toFixed(3)}` : "—"}</td>
                <td>
                  {Array.isArray(m.agent_roles) ? m.agent_roles.map((r: string) => (
                    <span key={r} className="pill" style={{ marginRight: 4, fontSize: 10 }}>{r}</span>
                  )) : (m.agent_role_key ?? "—")}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
