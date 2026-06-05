/**
 * PromptCoverageBar — 覆盖率进度条 (NF2 阶段1)
 *
 * 显示: "覆盖率: 82% (38/46)"
 * 颜色: <70%红, 70-90%黄, >90%绿
 */
export function PromptCoverageBar({ filled, total }: { filled: number; total: number }) {
  const pct = total > 0 ? Math.round((filled / total) * 100) : 0;
  const color = pct >= 90 ? "#4caf50" : pct >= 70 ? "#ff9800" : "#f44336";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
      <span className="muted" style={{ whiteSpace: "nowrap" }}>
        覆盖率: {pct}% ({filled}/{total})
      </span>
      <div
        style={{
          flex: 1,
          height: 8,
          background: "var(--bg-surface, #eee)",
          borderRadius: 4,
          overflow: "hidden",
          maxWidth: 200,
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: color,
            borderRadius: 4,
            transition: "width 0.3s ease",
          }}
        />
      </div>
    </div>
  );
}
