/**
 * AgentRunDetailPanel — 右侧详情 (P4 §6)
 *
 * 选中 Agent 后的详细面板: 头像 + 名称 + 状态 + 绑定模型 +
 * 健康 + 当前任务 + 实时日志 + 最近 10 次运行统计.
 */
import { useEffect, useState } from "react";
import type { AgentRoleMatrixItem, AgentRun } from "../../types";
import { AGENT_STATUS_LABEL } from "../../types";
import { AgentAvatar } from "./AgentAvatar";
import { getAgentRunEvents, getAgentRole, listAgentRuns, updateAgentModelBinding } from "../../api";

export function AgentRunDetailPanel({ item }: { item: AgentRoleMatrixItem | null }) {
  const [events, setEvents] = useState<any[]>([]);
  const [allRuns, setAllRuns] = useState<AgentRun[]>([]);
  const [editingBinding, setEditingBinding] = useState(false);
  const [draftModel, setDraftModel] = useState("");
  const [draftProvider, setDraftProvider] = useState<number | null>(null);

  useEffect(() => {
    if (!item) { setEvents([]); setAllRuns([]); return; }
    let cancelled = false;
    if (item.last_run_id) {
      getAgentRunEvents(item.last_run_id, 50)
        .then((d) => { if (!cancelled) setEvents(d); })
        .catch(() => { if (!cancelled) setEvents([]); });
    } else {
      setEvents(item.recent_events ?? []);
    }
    listAgentRuns({ agent_role_id: item.role.id, limit: 10 })
      .then((d) => { if (!cancelled) setAllRuns(d); })
      .catch(() => { if (!cancelled) setAllRuns([]); });
    return () => { cancelled = true; };
  }, [item]);

  if (!item) {
    return (
      <div className="agent-detail-panel">
        <div className="muted small" style={{ padding: 16 }}>点中间一个 Agent 行查看详细日志 / 改绑 / 启停。</div>
      </div>
    );
  }
  const r = item.role;
  const recent10 = allRuns.length > 0 ? allRuns : item.recent_runs;
  const totalInputTokens = recent10.reduce((s, x) => s + (x.input_tokens ?? 0), 0);
  const totalOutputTokens = recent10.reduce((s, x) => s + (x.output_tokens ?? 0), 0);
  const totalCost = recent10.reduce((s, x) => s + (x.cost_usd ?? 0), 0);
  const succeeded = recent10.filter((x) => x.status === "succeeded").length;
  const failed = recent10.filter((x) => x.status === "failed").length;

  return (
    <div className="agent-detail-panel">
      <div className="agent-detail-panel-head">
        <AgentAvatar style={r.avatar_style} status={item.status} size={48} />
        <div>
          <div style={{ fontSize: 14, fontWeight: 500 }}>{r.display_name}</div>
          <div className="muted small">{r.key} · {r.category} · {r.run_mode}</div>
        </div>
        <span className={`pill agent-status-pill agent-status-pill-${item.status}`} style={{ marginLeft: "auto" }}>
          {item.status_label}
        </span>
      </div>
      <div className="agent-detail-panel-body">
        <Section title="绑定模型">
          {item.binding ? (
            !editingBinding ? (
              <div className="agent-detail-binding">
                <div><span className="muted small">Provider</span> · {item.provider_name ?? `#${item.binding.provider_id}`}</div>
                <div><span className="muted small">Model</span> · {item.model_name ?? "—"}</div>
                {item.binding.temperature != null && (
                  <div><span className="muted small">Temperature</span> · {item.binding.temperature}</div>
                )}
                {item.binding.max_tokens != null && (
                  <div><span className="muted small">Max tokens</span> · {item.binding.max_tokens}</div>
                )}
                {item.binding.fallback_model_name && (
                  <div><span className="muted small">Fallback</span> · {item.binding.fallback_model_name}</div>
                )}
                <button className="tiny" onClick={() => {
                  setDraftModel(item.model_name ?? "");
                  setDraftProvider(item.binding?.provider_id ?? null);
                  setEditingBinding(true);
                }}>改绑</button>
              </div>
            ) : (
              <div className="agent-detail-binding-edit">
                <input
                  className="input"
                  placeholder="Provider ID"
                  value={draftProvider ?? ""}
                  onChange={(e) => setDraftProvider(e.target.value ? Number(e.target.value) : null)}
                />
                <input
                  className="input"
                  placeholder="Model"
                  value={draftModel}
                  onChange={(e) => setDraftModel(e.target.value)}
                />
                <div style={{ display: "flex", gap: 4 }}>
                  <button className="primary tiny" onClick={async () => {
                    try {
                      await updateAgentModelBinding(item.role.id, {
                        provider_id: draftProvider,
                        model_name: draftModel,
                      });
                      setEditingBinding(false);
                    } catch (e: any) {
                      alert(`改绑失败: ${e?.message ?? e}`);
                    }
                  }}>保存</button>
                  <button className="tiny" onClick={() => setEditingBinding(false)}>取消</button>
                </div>
              </div>
            )
          ) : (
            <div className="muted small">未绑定</div>
          )}
        </Section>
        <Section title="当前任务">
          {item.current_task ?? <span className="muted small">—</span>}
          {item.progress > 0 && (
            <div className="agent-role-row-progress" style={{ marginTop: 4 }}>
              <div className="agent-role-row-progress-fill" style={{ width: `${Math.round(item.progress * 100)}%` }} />
            </div>
          )}
        </Section>
        <Section title="实时日志">
          {events.length === 0 ? (
            <div className="muted small">无事件 (P4 §15 禁 6: 没有运行记录的 Agent 不假装运行)</div>
          ) : (
            <ul className="agent-detail-event-list">
              {events.slice(0, 20).map((ev) => (
                <li key={ev.id}>
                  <span className="muted small">{new Date(ev.created_at).toLocaleTimeString("zh-CN")}</span>
                  <span className="pill tiny">{ev.event_type}</span>
                  <span>{ev.message}</span>
                </li>
              ))}
            </ul>
          )}
        </Section>
        <Section title="最近 10 次运行">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 11 }}>
            <div><span className="muted small">完成</span> · {succeeded}</div>
            <div><span className="muted small">失败</span> · {failed}</div>
            <div><span className="muted small">In tokens</span> · {totalInputTokens.toLocaleString()}</div>
            <div><span className="muted small">Out tokens</span> · {totalOutputTokens.toLocaleString()}</div>
            <div><span className="muted small">成本</span> · ${totalCost.toFixed(4)}</div>
            <div><span className="muted small">总运行</span> · {recent10.length}</div>
          </div>
        </Section>
        {r.description && (
          <Section title="职责">
            <div className="muted small" style={{ lineHeight: 1.5 }}>{r.description}</div>
          </Section>
        )}
        {item.last_error && (
          <Section title="最近错误">
            <div className="agent-detail-error">⚠ {item.last_error}</div>
          </Section>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="agent-detail-section">
      <div className="agent-detail-section-title">{title}</div>
      <div className="agent-detail-section-body">{children}</div>
    </div>
  );
}
