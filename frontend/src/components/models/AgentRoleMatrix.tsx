/**
 * AgentRoleMatrix — 角色绑定矩阵 (P4 §4)
 *
 * 中间主区域. 按 category 分组 (writing / study / memory /
 * discussion / custom), 每一行是一个 AgentRoleRow. 顶部一个 chip
 * 行做状态过滤 (全部/待命/运行中/失败/禁用), 右上 "+ 新增 Agent"
 * 按钮触发 AgentRoleEditor.
 */
import { useMemo, useState } from "react";
import type { AgentCategory, AgentRoleMatrixItem, AgentStatus } from "../../types";
import { AGENT_CATEGORY_LABEL } from "../../types";
import { AgentRoleRow } from "./AgentRoleRow";
// CSS lives in src/styles/global.css (P4 block)

type FilterKey = "all" | AgentStatus;

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all",        label: "全部" },
  { key: "running",    label: "运行中" },
  { key: "failed",     label: "失败" },
  { key: "succeeded",  label: "完成" },
  { key: "idle",       label: "待命" },
  { key: "disabled",   label: "禁用" },
];

export function AgentRoleMatrix({
  items, onSelect, selectedId, onAddAgent, onEdit, onDelete,
}: {
  items: AgentRoleMatrixItem[];
  onSelect: (id: number) => void;
  selectedId: number | null;
  onAddAgent: () => void;
  onEdit: (id: number) => void;
  onDelete: (id: number) => void;
}) {
  const [filter, setFilter] = useState<FilterKey>("all");

  // 按 category 分组
  const grouped = useMemo(() => {
    const m: Record<string, AgentRoleMatrixItem[]> = {};
    for (const it of items) {
      const k = it.role.category;
      (m[k] ??= []).push(it);
    }
    return m;
  }, [items]);

  // 应用 filter
  const filterFn = (it: AgentRoleMatrixItem): boolean => {
    if (filter === "all") return true;
    return it.status === filter;
  };

  // 各状态的计数 (chip 上显示)
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const it of items) c[it.status] = (c[it.status] ?? 0) + 1;
    return c;
  }, [items]);

  // 按 P4 §10 顺序
  const categoryOrder: AgentCategory[] = ["writing", "memory", "study", "discussion", "review", "custom"];

  return (
    <div className="agent-role-matrix">
      <div className="agent-role-matrix-toolbar">
        <div className="agent-role-matrix-chips">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              className={`agent-role-chip ${filter === f.key ? "active" : ""}`}
              onClick={() => setFilter(f.key)}
            >
              {f.label} ({f.key === "all" ? items.length : (counts[f.key] ?? 0)})
            </button>
          ))}
        </div>
        <button className="primary" onClick={onAddAgent}>+ 新增 Agent</button>
      </div>
      {categoryOrder.map((cat) => {
        const list = (grouped[cat] ?? []).filter(filterFn);
        if (list.length === 0) return null;
        return (
          <div key={cat} className="agent-role-matrix-section">
            <h4 className="agent-role-matrix-section-title">
              {AGENT_CATEGORY_LABEL[cat]} <span className="muted small">({list.length})</span>
            </h4>
            {list.map((it) => (
              <AgentRoleRow
                key={it.role.id}
                item={it}
                selected={selectedId === it.role.id}
                onClick={() => onSelect(it.role.id)}
                onEdit={() => onEdit(it.role.id)}
                onDelete={() => onDelete(it.role.id)}
              />
            ))}
          </div>
        );
      })}
      {items.length === 0 && (
        <div className="empty-large">
          <div className="empty-large-glyph">⚙</div>
          <h3>还没有 Agent 角色</h3>
          <p>点右上「+ 新增 Agent」添加一个。</p>
        </div>
      )}
    </div>
  );
}
