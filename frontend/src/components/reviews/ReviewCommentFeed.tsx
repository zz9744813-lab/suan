import { useState } from "react";

/**
 * ReviewCommentFeed — 评论流组件 (NF2 阶段4)
 *
 * 显示评论列表，按时间排序
 * 每条: 读者Agent, 评论标题, 严重度, 证据引用
 */
export function ReviewCommentFeed({
  comments,
  onGroup,
}: {
  comments: any[];
  onGroup: (ids: number[]) => void;
}) {
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleGroup = () => {
    if (selected.size < 2) return;
    onGroup(Array.from(selected));
    setSelected(new Set());
  };

  const severityColor = (s: string) => {
    if (s === "high" || s === "critical") return { bg: "#fce4ec", color: "#c62828" };
    if (s === "medium" || s === "warning") return { bg: "#fff3e0", color: "#e65100" };
    return { bg: "#e8f5e9", color: "#2e7d32" };
  };

  if (comments.length === 0) {
    return <div className="muted" style={{ fontSize: 12, padding: 8 }}>暂无评论</div>;
  }

  return (
    <div>
      {selected.size >= 2 && (
        <div style={{ marginBottom: 8 }}>
          <button className="small primary" onClick={handleGroup}>
            合并为问题包 ({selected.size} 条)
          </button>
        </div>
      )}

      <div style={{ maxHeight: 480, overflow: "auto" }}>
        {comments.map((c, i) => {
          const id = c.id ?? i;
          const sc = severityColor(c.severity || "low");
          const isSelected = selected.has(id);

          return (
            <div
              key={id}
              style={{
                padding: "8px 10px",
                borderBottom: "1px solid var(--border, #eee)",
                background: isSelected ? "var(--bg-hover, #f0f0ff)" : "transparent",
                display: "flex",
                gap: 8,
                alignItems: "flex-start",
                fontSize: 12,
              }}
            >
              <input
                type="checkbox"
                checked={isSelected}
                onChange={() => toggleSelect(id)}
                style={{ marginTop: 2 }}
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                  <span style={{ fontWeight: 500, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {c.title || c.headline || `评论#${id}`}
                  </span>
                  <span
                    style={{
                      fontSize: 10,
                      padding: "1px 6px",
                      borderRadius: 3,
                      background: sc.bg,
                      color: sc.color,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {c.severity || "low"}
                  </span>
                </div>
                {c.reader_agent && (
                  <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>
                    {c.reader_agent}
                  </div>
                )}
                {c.content && (
                  <div style={{ fontSize: 11, color: "var(--text-secondary, #666)", marginBottom: 2, lineHeight: 1.4 }}>
                    {c.content.slice(0, 160)}
                  </div>
                )}
                {c.evidence && (
                  <div className="muted" style={{ fontSize: 10, fontStyle: "italic" }}>
                    证据: {typeof c.evidence === "string" ? c.evidence.slice(0, 80) : JSON.stringify(c.evidence).slice(0, 80)}
                  </div>
                )}
                {c.created_at && (
                  <div className="muted" style={{ fontSize: 10, marginTop: 2 }}>
                    {new Date(c.created_at).toLocaleString("zh-CN")}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
