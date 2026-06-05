/**
 * PromptRecommendationDrawer — 推荐详情抽屉 (NF2 阶段1)
 *
 * 显示推荐模板、评分、置信度、推荐原因、候选列表
 * 按钮: 应用/锁定/跳过
 */
export function PromptRecommendationDrawer({
  visible,
  data,
  onClose,
  onApply,
  onLock,
}: {
  visible: boolean;
  data: any;
  onClose: () => void;
  onApply: () => void;
  onLock: () => void;
}) {
  if (!visible || !data) return null;

  const candidates: any[] = data.candidates ?? [];

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        bottom: 0,
        width: 380,
        background: "var(--bg-card, #fff)",
        borderLeft: "1px solid var(--border, #ddd)",
        boxShadow: "-4px 0 16px rgba(0,0,0,0.1)",
        zIndex: 1000,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border, #ddd)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0, fontSize: 15 }}>推荐详情</h3>
        <button style={{ background: "none", border: "none", fontSize: 18, cursor: "pointer" }} onClick={onClose}>×</button>
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflow: "auto", padding: "16px 20px" }}>
        {/* Recommended template */}
        <div style={{ marginBottom: 16 }}>
          <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>推荐模板</div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>{data.template_name || data.template_key || "—"}</div>
        </div>

        {/* Scores */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
          <div>
            <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>评分</div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{data.score ?? "—"}</div>
          </div>
          <div>
            <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>置信度</div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>
              {data.confidence != null ? `${Math.round(data.confidence * 100)}%` : "—"}
            </div>
          </div>
        </div>

        {/* Reason */}
        {data.reason && (
          <div style={{ marginBottom: 16 }}>
            <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>推荐原因</div>
            <div style={{ fontSize: 13, lineHeight: 1.5 }}>{data.reason}</div>
          </div>
        )}

        {/* Candidates */}
        {candidates.length > 0 && (
          <div>
            <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>候选列表</div>
            {candidates.map((c: any, i: number) => (
              <div
                key={i}
                style={{
                  padding: "8px 10px",
                  borderRadius: 4,
                  border: "1px solid var(--border, #eee)",
                  marginBottom: 6,
                  fontSize: 12,
                  display: "flex",
                  justifyContent: "space-between",
                }}
              >
                <span>{c.template_name || c.template_key || `候选#${i + 1}`}</span>
                <span className="muted">{c.score != null ? `${c.score}` : ""}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer actions */}
      <div style={{ padding: "12px 20px", borderTop: "1px solid var(--border, #ddd)", display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button onClick={onClose}>跳过</button>
        <button onClick={onLock}>锁定</button>
        <button className="primary" onClick={onApply}>应用</button>
      </div>
    </div>
  );
}
