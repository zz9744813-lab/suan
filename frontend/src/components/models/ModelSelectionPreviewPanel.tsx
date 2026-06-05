/**
 * ModelSelectionPreviewPanel — 模型选择预览面板
 *
 * 展示系统为什么选这个模型: 最终选择的 Provider/Model/Score/Reason + 候选排序表格
 */
import type { PreviewSelectionResponse } from "../../api";

interface Props {
  data: PreviewSelectionResponse | null;
  loading: boolean;
}

export function ModelSelectionPreviewPanel({ data, loading }: Props) {
  if (loading) {
    return <div className="muted small" style={{ padding: 8 }}>正在预览选择…</div>;
  }
  if (!data) {
    return <div className="muted small" style={{ padding: 8 }}>点击 "预览选择" 查看推荐结果</div>;
  }

  const { selected, candidates } = data;

  return (
    <div>
      {/* 最终选择 */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, marginBottom: 8, fontSize: 12 }}>
        <div><span className="muted small">Provider</span> · {selected.provider_name ?? `#${selected.provider_id}`}</div>
        <div><span className="muted small">Model</span> · {selected.model_name}</div>
        <div><span className="muted small">Score</span> · {selected.score.toFixed(2)}</div>
        <div><span className="muted small">Risk</span> · {selected.risk.length > 0 ? selected.risk.join(", ") : "无"}</div>
      </div>
      {selected.health != null && (
        <div style={{ fontSize: 12, marginBottom: 4 }}>
          <span className="muted small">Health</span> · {selected.health.toFixed(2)}
          {selected.success_rate != null && ` · Success ${selected.success_rate.toFixed(0)}%`}
          {selected.latency_ms != null && ` · ${selected.latency_ms}ms`}
          {selected.cost_score != null && ` · Cost ${selected.cost_score.toFixed(2)}`}
        </div>
      )}

      {/* 候选排序 */}
      {candidates.length > 1 && (
        <details style={{ marginTop: 6 }}>
          <summary className="small" style={{ cursor: "pointer" }}>
            候选列表 ({candidates.length})
          </summary>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, marginTop: 4 }}>
            <thead>
              <tr>
                <th className="muted small" style={{ textAlign: "left", padding: "2px 4px" }}>#</th>
                <th className="muted small" style={{ textAlign: "left", padding: "2px 4px" }}>Provider</th>
                <th className="muted small" style={{ textAlign: "left", padding: "2px 4px" }}>Model</th>
                <th className="muted small" style={{ textAlign: "right", padding: "2px 4px" }}>Score</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((c, i) => (
                <tr key={`${c.provider_id}-${c.model_name}`} style={{ background: c === selected ? "rgba(255,255,255,0.05)" : undefined }}>
                  <td style={{ padding: "2px 4px" }}>{i + 1}</td>
                  <td style={{ padding: "2px 4px" }}>{c.provider_name ?? `#${c.provider_id}`}</td>
                  <td style={{ padding: "2px 4px" }}>{c.model_name}</td>
                  <td style={{ textAlign: "right", padding: "2px 4px" }}>{c.score.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </div>
  );
}
