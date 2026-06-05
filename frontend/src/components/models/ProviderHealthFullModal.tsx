/**
 * ProviderHealthFullModal — Provider 完整健康检查弹窗
 *
 * 调用 fullProviderHealth API, 展示每个模型的健康状态、推荐角色
 */
import { useEffect, useState } from "react";
import { fullProviderHealth } from "../../api";

interface Props {
  providerId: number | null;
  onClose: () => void;
}

export function ProviderHealthFullModal({ providerId, onClose }: Props) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (providerId == null) return;
    let cancelled = false;
    setLoading(true);
    setErr(null);
    fullProviderHealth(providerId)
      .then((res) => { if (!cancelled) setData(res); })
      .catch((e: any) => { if (!cancelled) setErr(e?.message ?? String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [providerId]);

  if (providerId == null) return null;

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}
      onClick={onClose}
    >
      <div
        style={{ background: "#1a1a1a", border: "1px solid #2e2e2e", borderRadius: 8, padding: 16, minWidth: 420, maxHeight: "80vh", overflow: "auto" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <span style={{ fontWeight: 500, fontSize: 14 }}>Provider #{providerId} 健康检查</span>
          <button className="tiny" onClick={onClose}>关闭</button>
        </div>

        {loading && <div className="muted small">正在检测…</div>}
        {err && <div className="small" style={{ color: "#f87171" }}>检测失败: {err}</div>}

        {data && (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, marginBottom: 12, fontSize: 12 }}>
              <div><span className="muted small">状态</span> · {data.status}</div>
              <div><span className="muted small">健康分</span> · {data.health_score?.toFixed(2) ?? "—"}</div>
              <div><span className="muted small">延迟</span> · {data.latency_ms != null ? `${data.latency_ms}ms` : "—"}</div>
            </div>

            {data.models && data.models.length > 0 && (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                <thead>
                  <tr>
                    <th className="muted small" style={{ textAlign: "left", padding: "2px 4px" }}>模型</th>
                    <th className="muted small" style={{ textAlign: "center", padding: "2px 4px" }}>可用</th>
                    <th className="muted small" style={{ textAlign: "right", padding: "2px 4px" }}>JSON</th>
                    <th className="muted small" style={{ textAlign: "right", padding: "2px 4px" }}>长输出</th>
                    <th className="muted small" style={{ textAlign: "right", padding: "2px 4px" }}>速度</th>
                    <th className="muted small" style={{ textAlign: "left", padding: "2px 4px" }}>推荐角色</th>
                  </tr>
                </thead>
                <tbody>
                  {data.models.map((m: any) => (
                    <tr key={m.model}>
                      <td style={{ padding: "2px 4px" }}>{m.model}</td>
                      <td style={{ textAlign: "center", padding: "2px 4px", color: m.available ? "#4ade80" : "#f87171" }}>
                        {m.available ? "✓" : "✕"}
                      </td>
                      <td style={{ textAlign: "right", padding: "2px 4px" }}>{m.json_score?.toFixed(1) ?? "—"}</td>
                      <td style={{ textAlign: "right", padding: "2px 4px" }}>{m.long_output_score?.toFixed(1) ?? "—"}</td>
                      <td style={{ textAlign: "right", padding: "2px 4px" }}>{m.speed_score?.toFixed(1) ?? "—"}</td>
                      <td style={{ padding: "2px 4px" }}>{(m.recommended_roles ?? []).join(", ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>
    </div>
  );
}
