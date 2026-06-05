/**
 * PromptCell — 矩阵单元格组件 (NF2 阶段1)
 *
 * 显示: 模板名称 + 匹配百分比, 状态标签
 * 悬浮: 推荐原因、历史效果、是否可覆盖
 * 点击: 打开推荐抽屉或绑定选择器
 */
import { useState } from "react";

export interface MatrixCell {
  agent_role_key: string;
  genre: string;
  template_id: number | null;
  template_name: string | null;
  match_pct: number;
  state: "manual" | "auto" | "system_seed" | "locked" | "suggest" | "missing";
  recommendation?: {
    reason: string;
    historical_effect?: string;
    overridable: boolean;
  };
}

const STATE_LABELS: Record<string, { label: string; bg: string; color: string }> = {
  manual: { label: "手动", bg: "#e3f2fd", color: "#1565c0" },
  auto: { label: "自动", bg: "#e8f5e9", color: "#2e7d32" },
  system_seed: { label: "种子", bg: "#fff3e0", color: "#e65100" },
  locked: { label: "锁定", bg: "#fce4ec", color: "#c62828" },
  suggest: { label: "建议", bg: "#f3e5f5", color: "#6a1b9a" },
  missing: { label: "空缺", bg: "#fafafa", color: "#9e9e9e" },
};

export function PromptCell({
  cell,
  onLock,
  onUnlock,
  onRebind,
}: {
  cell: MatrixCell;
  onLock: () => void;
  onUnlock: () => void;
  onRebind: (templateId: number) => void;
}) {
  const [hover, setHover] = useState(false);
  const s = STATE_LABELS[cell.state] || STATE_LABELS.missing;

  return (
    <div
      style={{
        position: "relative",
        padding: "6px 8px",
        minHeight: 52,
        borderRadius: 4,
        border: "1px solid var(--border, #ddd)",
        background: hover ? "var(--bg-hover, #f5f5f5)" : "var(--bg-card, #fff)",
        cursor: "pointer",
        transition: "background 0.15s",
      }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onClick={() => {
        if (cell.template_id) onRebind(cell.template_id);
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 2 }}>
        <span style={{ fontSize: 12, fontWeight: 600, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {cell.template_name || "---"}
        </span>
        {cell.match_pct > 0 && (
          <span className="tiny" style={{ color: "var(--text-secondary, #888)" }}>
            {cell.match_pct}%
          </span>
        )}
      </div>
      <span
        style={{
          display: "inline-block",
          fontSize: 10,
          padding: "1px 6px",
          borderRadius: 3,
          background: s.bg,
          color: s.color,
          lineHeight: "16px",
        }}
      >
        {s.label}
      </span>

      {/* Hover tooltip */}
      {hover && cell.recommendation && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            zIndex: 100,
            background: "var(--bg-card, #fff)",
            border: "1px solid var(--border, #ddd)",
            borderRadius: 6,
            padding: 10,
            minWidth: 200,
            boxShadow: "0 4px 12px rgba(0,0,0,0.12)",
            fontSize: 12,
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <div style={{ fontWeight: 600, marginBottom: 4 }}>推荐原因</div>
          <div style={{ color: "var(--text-secondary, #666)", marginBottom: 6 }}>{cell.recommendation.reason}</div>
          {cell.recommendation.historical_effect && (
            <>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>历史效果</div>
              <div style={{ color: "var(--text-secondary, #666)", marginBottom: 6 }}>{cell.recommendation.historical_effect}</div>
            </>
          )}
          <div style={{ fontSize: 11, color: "var(--text-tertiary, #999)" }}>
            {cell.recommendation.overridable ? "可覆盖" : "不可覆盖"}
          </div>
          <div style={{ display: "flex", gap: 4, marginTop: 6 }}>
            {cell.state === "locked" ? (
              <button className="tiny" onClick={onUnlock}>解锁</button>
            ) : (
              <button className="tiny" onClick={onLock}>锁定</button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
