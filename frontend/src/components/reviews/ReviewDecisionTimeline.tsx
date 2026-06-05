/**
 * ReviewDecisionTimeline — 裁决时间线 (NF2 阶段4)
 *
 * 显示讨论→裁决→返工→复评的完整流程
 */
export function ReviewDecisionTimeline({ decisions }: { decisions: any[] }) {
  if (decisions.length === 0) {
    return <div className="muted" style={{ fontSize: 12, padding: 8 }}>暂无裁决记录</div>;
  }

  const stageColor = (stage: string) => {
    switch (stage) {
      case "discussion": return "#2196f3";
      case "decision": return "#9c27b0";
      case "rewrite": return "#ff9800";
      case "re_review": return "#4caf50";
      case "done": return "#4caf50";
      default: return "#bdbdbd";
    }
  };

  const stageLabel = (stage: string) => {
    switch (stage) {
      case "discussion": return "讨论";
      case "decision": return "裁决";
      case "rewrite": return "返工";
      case "re_review": return "复评";
      case "done": return "完成";
      default: return stage;
    }
  };

  return (
    <div style={{ padding: 12 }}>
      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 10 }}>裁决时间线</div>
      <div style={{ position: "relative", paddingLeft: 16 }}>
        {decisions.map((d, i) => {
          const stage = d.stage ?? d.status ?? "discussion";
          const color = stageColor(stage);
          return (
            <div
              key={d.id ?? i}
              style={{
                position: "relative",
                paddingBottom: 16,
                borderLeft: "2px solid var(--border, #ddd)",
                marginLeft: -6,
                paddingLeft: 18,
              }}
            >
              {/* Dot */}
              <div
                style={{
                  position: "absolute",
                  left: -6,
                  top: 2,
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  background: color,
                  border: "2px solid var(--bg-card, #fff)",
                }}
              />
              <div style={{ fontSize: 12 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                  <span style={{ fontWeight: 600, color }}>{stageLabel(stage)}</span>
                  <span className="muted" style={{ fontSize: 10 }}>
                    {d.created_at ? new Date(d.created_at).toLocaleString("zh-CN") : ""}
                  </span>
                </div>
                <div style={{ color: "var(--text-secondary, #666)", lineHeight: 1.4 }}>
                  {d.summary || d.content || d.reason || "—"}
                </div>
                {d.actor && (
                  <div className="muted" style={{ fontSize: 10 }}>由 {d.actor}</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
