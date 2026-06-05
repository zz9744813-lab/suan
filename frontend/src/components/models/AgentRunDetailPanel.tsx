/**
 * AgentRunDetailPanel — 右侧详情 (P4 §6, P0-Model-Failover 改造)
 *
 * 选中 Agent 后的详细面板: 头像 + 名称 + 状态 + 绑定模型(含模式切换) +
 * 自动策略 + 候选 Provider + Fallback 编辑器 + 预览面板 +
 * Failover 时间线 + 熔断器徽标 + 健康 + 当前任务 + 实时日志 + 最近 10 次运行统计.
 */
import { useEffect, useState } from "react";
import type { AgentRoleMatrixItem, AgentRun } from "../../types";
import { AGENT_STATUS_LABEL } from "../../types";
import { AgentAvatar } from "./AgentAvatar";
import {
  getAgentRunEvents,
  listAgentRuns,
  updateAgentModelBinding,
  listProviders,
  previewModelSelection,
  listModelCallEvents,
} from "../../api";
import type { PreviewSelectionResponse } from "../../api";
import { BindingModeSwitch } from "./BindingModeSwitch";
import { AutoStrategySelect } from "./AutoStrategySelect";
import { CandidateProviderPicker } from "./CandidateProviderPicker";
import { FallbackCandidateEditor } from "./FallbackCandidateEditor";
import { ModelSelectionPreviewPanel } from "./ModelSelectionPreviewPanel";
import { ModelFailoverTimeline } from "./ModelFailoverTimeline";
import { CircuitBreakerBadge } from "./CircuitBreakerBadge";
import { ProviderHealthFullModal } from "./ProviderHealthFullModal";
import { AutoConfigureToolbar } from "./AutoConfigureToolbar";

type BindingMode = "auto" | "manual" | "manual_with_fallback";

export function AgentRunDetailPanel({ item }: { item: AgentRoleMatrixItem | null }) {
  const [events, setEvents] = useState<any[]>([]);
  const [allRuns, setAllRuns] = useState<AgentRun[]>([]);
  const [editingBinding, setEditingBinding] = useState(false);

  // binding edit state
  const [draftMode, setDraftMode] = useState<BindingMode>("auto");
  const [draftModel, setDraftModel] = useState("");
  const [draftProvider, setDraftProvider] = useState<number | null>(null);
  const [draftStrategy, setDraftStrategy] = useState("quality_first");
  const [draftCandidateProviderIds, setDraftCandidateProviderIds] = useState<number[]>([]);
  const [draftFallbackCandidates, setDraftFallbackCandidates] = useState<{ provider_id: number; model_name: string }[]>([]);
  const [draftAllowAutoFallback, setDraftAllowAutoFallback] = useState(true);

  // providers list for picker
  const [providers, setProviders] = useState<any[]>([]);

  // preview panel
  const [previewData, setPreviewData] = useState<PreviewSelectionResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // failover timeline
  const [failoverEvents, setFailoverEvents] = useState<any[]>([]);
  const [failoverLoading, setFailoverLoading] = useState(false);

  // provider health modal
  const [healthProviderId, setHealthProviderId] = useState<number | null>(null);

  // circuit breaker state (derived from binding)
  const [circuitState, setCircuitState] = useState("closed");
  const [circuitOpenUntil, setCircuitOpenUntil] = useState<string | null>(null);

  useEffect(() => {
    listProviders().then(setProviders).catch(() => {});
  }, []);

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

    // load failover timeline
    setFailoverLoading(true);
    listModelCallEvents({ agent_role_key: item.role.key, limit: 20 })
      .then((d) => { if (!cancelled) setFailoverEvents(Array.isArray(d) ? d : []); })
      .catch(() => { if (!cancelled) setFailoverEvents([]); })
      .finally(() => { if (!cancelled) setFailoverLoading(false); });

    return () => { cancelled = true; };
  }, [item]);

  // When entering edit mode, initialize draft from current binding
  function startEditBinding() {
    if (!item?.binding) {
      setDraftMode("auto");
      setDraftModel("");
      setDraftProvider(null);
      setDraftStrategy("quality_first");
      setDraftCandidateProviderIds([]);
      setDraftFallbackCandidates([]);
      setDraftAllowAutoFallback(true);
    } else {
      const b = item.binding;
      setDraftMode(b.selection_mode ?? "auto");
      setDraftModel(b.model_name ?? "");
      setDraftProvider(b.provider_id);
      setDraftStrategy(b.auto_strategy ?? "quality_first");
      setDraftCandidateProviderIds(b.candidate_provider_ids ?? []);
      setDraftFallbackCandidates(
        (b.fallback_candidates_json ?? []).map((c) => ({ provider_id: c.provider_id, model_name: c.model }))
      );
      setDraftAllowAutoFallback(b.allow_auto_fallback ?? true);
      // derive circuit state from recent events if available
      setCircuitState((b as any).circuit_state ?? "closed");
      setCircuitOpenUntil((b as any).circuit_open_until ?? null);
    }
    setEditingBinding(true);
  }

  async function saveBinding() {
    if (!item) return;
    try {
      const body: any = {
        selection_mode: draftMode,
        provider_id: draftProvider,
        model_name: draftModel || null,
        auto_strategy: draftStrategy,
        candidate_provider_ids: draftCandidateProviderIds.length > 0 ? draftCandidateProviderIds : null,
        fallback_candidates_json: draftFallbackCandidates.length > 0
          ? draftFallbackCandidates.map((c) => ({ provider_id: c.provider_id, model: c.model_name, weight: 1 }))
          : null,
        allow_auto_fallback: draftAllowAutoFallback,
      };
      await updateAgentModelBinding(item.role.id, body);
      setEditingBinding(false);
    } catch (e: any) {
      alert(`改绑失败: ${e?.message ?? e}`);
    }
  }

  async function handlePreview() {
    if (!item) return;
    setPreviewLoading(true);
    try {
      const res = await previewModelSelection(item.role.id, {
        selection_mode: draftMode,
        auto_strategy: draftStrategy,
        candidate_provider_ids: draftCandidateProviderIds,
        agent_role_key: item.role.key,
      });
      setPreviewData(res);
    } catch {
      setPreviewData(null);
    } finally {
      setPreviewLoading(false);
    }
  }

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

  const currentBinding = item.binding;
  const currentMode: BindingMode = currentBinding?.selection_mode ?? "auto";

  // derive circuit state from binding extras if available
  const cState = (currentBinding as any)?.circuit_state ?? circuitState;
  const cOpenUntil = (currentBinding as any)?.circuit_open_until ?? circuitOpenUntil;

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
        {/* ── 绑定模型 Section (改造) ─────────────────── */}
        <Section title="绑定模型">
          {!editingBinding ? (
            <div className="agent-detail-binding">
              {/* 模式显示 */}
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <BindingModeSwitch value={currentMode} onChange={() => {}} disabled />
                <CircuitBreakerBadge state={cState} openUntil={cOpenUntil} />
              </div>

              {currentBinding ? (
                <>
                  <div><span className="muted small">Provider</span> · {item.provider_name ?? `#${currentBinding.provider_id}`}</div>
                  <div><span className="muted small">Model</span> · {item.model_name ?? "—"}</div>
                  {currentMode === "auto" && (
                    <div><span className="muted small">策略</span> · {currentBinding.auto_strategy ?? "—"}</div>
                  )}
                  {currentBinding.temperature != null && (
                    <div><span className="muted small">Temperature</span> · {currentBinding.temperature}</div>
                  )}
                  {currentBinding.max_tokens != null && (
                    <div><span className="muted small">Max tokens</span> · {currentBinding.max_tokens}</div>
                  )}
                  {currentBinding.fallback_model_name && (
                    <div><span className="muted small">Fallback</span> · {currentBinding.fallback_model_name}</div>
                  )}
                </>
              ) : (
                <div className="muted small">未绑定</div>
              )}

              {currentBinding?.last_selection_reason && (
                <div className="muted small" style={{ marginTop: 4 }}>
                  选择原因: {currentBinding.last_selection_reason}
                  {currentBinding.last_selection_score != null && ` (score: ${currentBinding.last_selection_score.toFixed(2)})`}
                </div>
              )}

              <div style={{ display: "flex", gap: 4, marginTop: 6 }}>
                <button className="tiny" onClick={startEditBinding}>改绑</button>
                {currentBinding?.provider_id && (
                  <button className="tiny" onClick={() => setHealthProviderId(currentBinding.provider_id!)}>
                    健康检查
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="agent-detail-binding-edit">
              {/* 模式切换 */}
              <div style={{ marginBottom: 8 }}>
                <div className="muted small" style={{ marginBottom: 4 }}>绑定模式</div>
                <BindingModeSwitch value={draftMode} onChange={setDraftMode} />
              </div>

              {/* auto 模式: 策略 + 候选 Provider + 预览 */}
              {draftMode === "auto" && (
                <>
                  <div style={{ marginBottom: 8 }}>
                    <div className="muted small" style={{ marginBottom: 4 }}>自动策略</div>
                    <AutoStrategySelect value={draftStrategy} onChange={setDraftStrategy} />
                  </div>
                  <div style={{ marginBottom: 8 }}>
                    <div className="muted small" style={{ marginBottom: 4 }}>候选 Provider</div>
                    <CandidateProviderPicker
                      providerIds={draftCandidateProviderIds}
                      onChange={setDraftCandidateProviderIds}
                      providers={providers.map((p) => ({ id: p.id, name: p.name, enabled: p.enabled }))}
                    />
                  </div>
                  <div style={{ marginBottom: 8 }}>
                    <button className="tiny primary" onClick={handlePreview} disabled={previewLoading}>
                      {previewLoading ? "预览中…" : "预览选择"}
                    </button>
                    <ModelSelectionPreviewPanel data={previewData} loading={previewLoading} />
                  </div>
                </>
              )}

              {/* manual 模式: provider/model 下拉 */}
              {(draftMode === "manual" || draftMode === "manual_with_fallback") && (
                <div style={{ marginBottom: 8 }}>
                  <div className="muted small" style={{ marginBottom: 4 }}>主模型</div>
                  <div style={{ display: "flex", gap: 4 }}>
                    <select
                      className="input"
                      value={draftProvider ?? ""}
                      onChange={(e) => setDraftProvider(e.target.value ? Number(e.target.value) : null)}
                      style={{ flex: 1 }}
                    >
                      <option value="">选择 Provider</option>
                      {providers.filter((p) => p.enabled).map((p) => (
                        <option key={p.id} value={p.id}>{p.name} (#{p.id})</option>
                      ))}
                    </select>
                    <input
                      className="input"
                      placeholder="Model 名称"
                      value={draftModel}
                      onChange={(e) => setDraftModel(e.target.value)}
                      style={{ flex: 1 }}
                    />
                  </div>
                </div>
              )}

              {/* manual_with_fallback: fallback 编辑器 */}
              {draftMode === "manual_with_fallback" && (
                <div style={{ marginBottom: 8 }}>
                  <div className="muted small" style={{ marginBottom: 4 }}>Fallback 候选</div>
                  <FallbackCandidateEditor
                    candidates={draftFallbackCandidates}
                    onChange={setDraftFallbackCandidates}
                    allowAutoFallback={draftAllowAutoFallback}
                    onAllowChange={setDraftAllowAutoFallback}
                  />
                </div>
              )}

              {/* 自动配置工具栏 */}
              <div style={{ marginBottom: 8 }}>
                <AutoConfigureToolbar
                  roleId={r.id}
                  agentRoleKey={r.key}
                  onConfigured={() => setEditingBinding(false)}
                />
              </div>

              <div style={{ display: "flex", gap: 4 }}>
                <button className="primary tiny" onClick={saveBinding}>保存</button>
                <button className="tiny" onClick={() => setEditingBinding(false)}>取消</button>
              </div>
            </div>
          )}
        </Section>

        {/* ── Failover 时间线 (始终显示) ────────────────── */}
        <Section title="Failover 时间线">
          <ModelFailoverTimeline events={failoverEvents} loading={failoverLoading} />
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

      {/* Provider 健康检查弹窗 */}
      <ProviderHealthFullModal providerId={healthProviderId} onClose={() => setHealthProviderId(null)} />
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
