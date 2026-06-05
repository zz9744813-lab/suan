/**
 * AgentRoleRow — 矩阵里的一行 (P4 §4)
 *
 * 显示: 头像 / 名称 / 描述 / 绑定的 provider+model / 当前状态 /
 * 进度条 / 展开按钮. 状态点用 AGENT_STATUS_LABEL 显示.
 */
import { useState } from "react";
import type { AgentRoleMatrixItem } from "../../types";
import { AgentAvatar } from "./AgentAvatar";

export function AgentRoleRow({
  item, selected, onClick, onEdit, onDelete,
}: {
  item: AgentRoleMatrixItem;
  selected: boolean;
  onClick: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const r = item.role;
  const pct = Math.round((item.progress || 0) * 100);
  const statusClass = item.status;
  return (
    <div className={`agent-role-row ${selected ? "selected" : ""}`} data-status={statusClass}>
      <div className="agent-role-row-main" onClick={onClick}>
        <AgentAvatar
          style={r.avatar_style}
          status={item.status}
          size={36}
          title={`${r.display_name} · ${item.status_label}`}
        />
        <div className="agent-role-row-info">
          <div className="agent-role-row-name">
            <b>{r.display_name}</b>
            <span className="muted small">· {r.key}</span>
            {!r.enabled && <span className="pill tiny gray" style={{ marginLeft: 6 }}>禁用</span>}
          </div>
          <div className="agent-role-row-desc" title={r.description ?? ""}>
            {r.description ?? "—"}
          </div>
        </div>
        <div className="agent-role-row-binding">
          {item.binding ? (
            <>
              <div className="agent-role-row-binding-provider">
                <span className="muted small">Provider</span>
                <span>{item.provider_name ?? `#${item.binding.provider_id}`}</span>
              </div>
              <div className="agent-role-row-binding-model">
                <span className="muted small">Model</span>
                <span>{item.model_name ?? "—"}</span>
              </div>
              {/* P0-MODEL-FAILOVER: 选模模式徽章 */}
              <div className="agent-role-row-mode">
                <span className={`pill tiny mode-${item.binding.selection_mode ?? "auto"}`} title={`auto_strategy: ${item.binding.auto_strategy ?? "—"}`}>
                  {item.binding.selection_mode === "manual" ? "🔒 手动" : item.binding.selection_mode === "manual_with_fallback" ? "🔒+备" : "⚙ 自动"}
                </span>
              </div>
            </>
          ) : (
            <span className="muted small">未绑定</span>
          )}
        </div>
        <div className="agent-role-row-status">
          <span className={`pill tiny agent-status-pill agent-status-pill-${statusClass}`}>
            {item.status_label}
          </span>
          {item.current_task && (
            <div className="agent-role-row-current muted small" title={item.current_task}>
              {item.current_task.slice(0, 30)}{item.current_task.length > 30 ? "…" : ""}
            </div>
          )}
          {pct > 0 && pct < 100 && (
            <div className="agent-role-row-progress">
              <div className="agent-role-row-progress-fill" style={{ width: `${pct}%` }} />
            </div>
          )}
        </div>
        <div className="agent-role-row-actions" onClick={(e) => e.stopPropagation()}>
          <button
            className="tiny"
            onClick={() => setExpanded((v) => !v)}
            title={expanded ? "收起" : "展开"}
          >
            {expanded ? "▾" : "▸"}
          </button>
          <button className="tiny" onClick={onEdit} title="编辑">✎</button>
          <button className="tiny danger" onClick={onDelete} title="删除" disabled={r.key === "planner" || r.key === "drafter"}>
            ✕
          </button>
        </div>
      </div>
      {expanded && (
        <div className="agent-role-row-expand">
          {item.last_run_id ? (
            <>
              <div className="agent-role-row-stat">
                <span className="muted small">最近 run</span>
                <span>#{item.last_run_id}</span>
              </div>
              <div className="agent-role-row-stat">
                <span className="muted small">耗时</span>
                <span>{item.recent_runs[0]?.elapsed_ms ? `${(item.recent_runs[0].elapsed_ms / 1000).toFixed(1)}s` : "—"}</span>
              </div>
              <div className="agent-role-row-stat">
                <span className="muted small">Token</span>
                <span>
                  {item.recent_runs[0]?.input_tokens ?? 0} → {item.recent_runs[0]?.output_tokens ?? 0}
                </span>
              </div>
              <div className="agent-role-row-stat">
                <span className="muted small">历史</span>
                <span>{item.total_runs} 次</span>
              </div>
            </>
          ) : (
            <div className="muted small">无运行记录 (P4 §15 禁 6: 没有运行记录的 Agent 不假装运行)</div>
          )}
          {item.last_error && (
            <div className="agent-role-row-error">⚠ {item.last_error}</div>
          )}
          {item.recent_events.length > 0 && (
            <div className="agent-role-row-events">
              <div className="muted small" style={{ marginTop: 6, marginBottom: 2 }}>最近事件 (前 5)</div>
              {item.recent_events.slice(0, 5).map((ev) => (
                <div key={ev.id} className="agent-role-row-event">
                  <span className="muted small">{new Date(ev.created_at).toLocaleTimeString("zh-CN")}</span>
                  <span className="pill tiny">{ev.event_type}</span>
                  <span>{ev.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
