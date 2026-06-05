/**
 * ReviewGroupPanel — 问题包/分组面板 (NF2 阶段4)
 *
 * 显示 ReviewCommentGroup 列表
 * 每组: 严重度, 评论数, decision, 是否已讨论
 */
export function ReviewGroupPanel({
  groups,
  onDiscuss,
}: {
  groups: any[];
  onDiscuss: (groupId: number) => void;
}) {
  if (groups.length === 0) {
    return <div className="muted" style={{ fontSize: 12, padding: 8 }}>暂无问题分组</div>;
  }

  const severityColor = (s: string) => {
    if (s === "high" || s === "critical") return { bg: "#fce4ec", color: "#c62828" };
    if (s === "medium" || s === "warning") return { bg: "#fff3e0", color: "#e65100" };
    return { bg: "#e8f5e9", color: "#2e7d32" };
  };

  return (
    <div>
      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>问题分组</div>
      <div style={{ maxHeight: 400, overflow: "auto" }}>
        {groups.map((g, i) => {
          const id = g.id ?? i;
          const sc = severityColor(g.severity || "low");
          const hasDiscussed = g.discussed === true || g.discussion_id != null;

          return (
            <div
              key={id}
              style={{
                padding: 10,
                marginBottom: 6,
                borderRadius: 4,
                border: "1px solid var(--border, #eee)",
                fontSize: 12,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                <span style={{ fontWeight: 600, flex: 1 }}>{g.title || `问题包 #${id}`}</span>
                <span
                  style={{
                    fontSize: 10,
                    padding: "1px 6px",
                    borderRadius: 3,
                    background: sc.bg,
                    color: sc.color,
                  }}
                >
                  {g.severity || "low"}
                </span>
              </div>
              <div style={{ display: "flex", gap: 12, marginBottom: 6 }}>
                <span className="muted" style={{ fontSize: 11 }}>{g.comment_count ?? g.comments?.length ?? 0} 条评论</span>
                {g.decision && (
                  <span className="muted" style={{ fontSize: 11 }}>
                    裁决: {g.decision}
                  </span>
                )}
                <span
                  className="pill"
                  style={{
                    fontSize: 10,
                    background: hasDiscussed ? "#e8f5e9" : "#fff3e0",
                    color: hasDiscussed ? "#2e7d32" : "#e65100",
                  }}
                >
                  {hasDiscussed ? "已讨论" : "待讨论"}
                </span>
              </div>
              {!hasDiscussed && (
                <button className="tiny primary" onClick={() => onDiscuss(id)}>
                  发起讨论
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
