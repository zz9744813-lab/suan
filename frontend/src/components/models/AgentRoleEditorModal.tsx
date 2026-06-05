/**
 * AgentRoleEditorModal — Agent 角色 3-Tab 编辑弹窗
 *
 * Tab 1: 基础信息 (名称/分类/阶段/超时/重试等)
 * Tab 2: 模型绑定 (Provider/Model/绑定模式/fallback/温度等)
 * Tab 3: Prompt 绑定 (system/task prompt 模板 + 输出格式)
 */
import { useEffect, useState } from "react";
import type {
  AgentAvatarStyle,
  AgentCategory,
  AgentRole,
  AgentRoleUpdateBody,
  AgentModelBinding,
  AgentPromptBinding,
  PromptTemplate,
  ModelProvider,
} from "../../types";
import {
  AGENT_AVATAR_STYLES,
  AGENT_CATEGORY_LABEL,
} from "../../types";
import {
  updateAgentRole,
  updateAgentModelBinding,
  updateAgentPromptBinding,
  listProviders,
  listPromptTemplates,
  previewModelSelection,
} from "../../api";
import type { PreviewSelectionResponse } from "../../api";
import { BindingModeSwitch } from "./BindingModeSwitch";
import { AutoStrategySelect } from "./AutoStrategySelect";
import { CandidateProviderPicker } from "./CandidateProviderPicker";
import { FallbackCandidateEditor } from "./FallbackCandidateEditor";
import { ModelSelectionPreviewPanel } from "./ModelSelectionPreviewPanel";

type BindingMode = "auto" | "manual" | "manual_with_fallback";

const CATEGORIES: AgentCategory[] = ["writing", "memory", "study", "discussion", "custom"];
const RUN_MODES: string[] = ["manual", "pipeline", "scheduled", "event"];
const TABS = ["基础信息", "模型绑定", "Prompt 绑定"] as const;
type TabKey = (typeof TABS)[number];

export function AgentRoleEditorModal({
  open,
  role,
  binding,
  promptBinding,
  onClose,
  onSaved,
}: {
  open: boolean;
  role: AgentRole;
  binding: AgentModelBinding | null;
  promptBinding: AgentPromptBinding | null;
  onClose: () => void;
  onSaved?: () => void;
}) {
  const [tab, setTab] = useState<TabKey>("基础信息");
  const [saving, setSaving] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  // ── Tab 1: 基础信息 state ──────────────────────────
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState<AgentCategory>("writing");
  const [avatarStyle, setAvatarStyle] = useState<AgentAvatarStyle>("scribe");
  const [enabled, setEnabled] = useState(true);
  const [visibleInMatrix, setVisibleInMatrix] = useState(true);
  const [runMode, setRunMode] = useState("pipeline");
  const [pipelineStage, setPipelineStage] = useState("");
  const [timeoutSeconds, setTimeoutSeconds] = useState(120);
  const [maxRetries, setMaxRetries] = useState(2);
  const [concurrencyLimit, setConcurrencyLimit] = useState(1);
  const [costLimit, setCostLimit] = useState("");

  // ── Tab 2: 模型绑定 state ─────────────────────────
  const [draftMode, setDraftMode] = useState<BindingMode>("auto");
  const [draftProvider, setDraftProvider] = useState<number | null>(null);
  const [draftModel, setDraftModel] = useState("");
  const [draftStrategy, setDraftStrategy] = useState("quality_first");
  const [draftCandidateProviderIds, setDraftCandidateProviderIds] = useState<number[]>([]);
  const [draftFallbackCandidates, setDraftFallbackCandidates] = useState<{ provider_id: number; model_name: string }[]>([]);
  const [draftAllowAutoFallback, setDraftAllowAutoFallback] = useState(true);
  const [draftTemperature, setDraftTemperature] = useState(0.7);
  const [draftMaxTokens, setDraftMaxTokens] = useState(4096);
  const [draftTopP, setDraftTopP] = useState(1.0);
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [previewData, setPreviewData] = useState<PreviewSelectionResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // ── Tab 3: Prompt 绑定 state ────────────────────────
  const [systemPromptId, setSystemPromptId] = useState<number | null>(null);
  const [taskPromptId, setTaskPromptId] = useState<number | null>(null);
  const [strictJson, setStrictJson] = useState(false);
  const [evidenceRequired, setEvidenceRequired] = useState(false);
  const [promptTemplates, setPromptTemplates] = useState<PromptTemplate[]>([]);

  // ── 初始化 ──────────────────────────────────────────
  useEffect(() => {
    if (!open) return;
    setErrMsg(null);
    setTab("基础信息");

    // Tab 1
    setDisplayName(role.display_name);
    setDescription(role.description ?? "");
    setCategory(role.category);
    setAvatarStyle((role.avatar_style ?? "scribe") as AgentAvatarStyle);
    setEnabled(role.enabled);
    setVisibleInMatrix(role.visible_in_matrix);
    setRunMode(role.run_mode);
    setPipelineStage(role.pipeline_stage ?? "");
    setTimeoutSeconds(role.timeout_seconds);
    setMaxRetries(role.max_retries);
    setConcurrencyLimit(role.concurrency_limit);
    setCostLimit(role.cost_limit_usd != null ? String(role.cost_limit_usd) : "");

    // Tab 2
    if (binding) {
      setDraftMode(binding.selection_mode ?? "auto");
      setDraftProvider(binding.provider_id);
      setDraftModel(binding.model_name ?? "");
      setDraftStrategy(binding.auto_strategy ?? "quality_first");
      setDraftCandidateProviderIds(binding.candidate_provider_ids ?? []);
      setDraftFallbackCandidates(
        (binding.fallback_candidates_json ?? []).map((c) => ({ provider_id: c.provider_id, model_name: c.model })),
      );
      setDraftAllowAutoFallback(binding.allow_auto_fallback ?? true);
      setDraftTemperature(binding.temperature ?? 0.7);
      setDraftMaxTokens(binding.max_tokens ?? 4096);
      setDraftTopP((binding.extra_body as any)?.top_p ?? 1.0);
    } else {
      setDraftMode("auto");
      setDraftProvider(null);
      setDraftModel("");
      setDraftStrategy("quality_first");
      setDraftCandidateProviderIds([]);
      setDraftFallbackCandidates([]);
      setDraftAllowAutoFallback(true);
      setDraftTemperature(0.7);
      setDraftMaxTokens(4096);
      setDraftTopP(1.0);
    }
    setPreviewData(null);

    // Tab 3
    if (promptBinding) {
      setSystemPromptId(promptBinding.system_prompt_template_id);
      setTaskPromptId(promptBinding.task_prompt_template_id);
      setStrictJson(promptBinding.strict_json);
      setEvidenceRequired(promptBinding.evidence_required);
    } else {
      setSystemPromptId(null);
      setTaskPromptId(null);
      setStrictJson(false);
      setEvidenceRequired(false);
    }

    // Load providers + templates
    listProviders().then(setProviders).catch(() => {});
    listPromptTemplates().then(setPromptTemplates).catch(() => {});
  }, [open, role, binding, promptBinding]);

  if (!open) return null;

  // ── 保存 ────────────────────────────────────────────
  const handleSave = async () => {
    setErrMsg(null);
    setSaving(true);
    try {
      // 1) 保存基础信息
      const roleBody: AgentRoleUpdateBody = {
        display_name: displayName,
        description: description || null,
        category,
        avatar_style: avatarStyle,
        enabled,
        visible_in_matrix: visibleInMatrix,
        run_mode: runMode as any,
        pipeline_stage: pipelineStage || null,
        timeout_seconds: timeoutSeconds,
        max_retries: maxRetries,
        concurrency_limit: concurrencyLimit,
        cost_limit_usd: costLimit ? Number(costLimit) : null,
      };
      await updateAgentRole(role.id, roleBody);

      // 2) 保存模型绑定
      await updateAgentModelBinding(role.id, {
        selection_mode: draftMode,
        provider_id: draftProvider,
        model_name: draftModel || null,
        auto_strategy: draftStrategy as any,
        candidate_provider_ids: draftCandidateProviderIds.length > 0 ? draftCandidateProviderIds : null,
        fallback_candidates_json: draftFallbackCandidates.length > 0
          ? draftFallbackCandidates.map((c) => ({ provider_id: c.provider_id, model: c.model_name, weight: 1 }))
          : null,
        allow_auto_fallback: draftAllowAutoFallback,
        temperature: draftTemperature,
        max_tokens: draftMaxTokens,
        extra_body: { top_p: draftTopP },
      });

      // 3) 保存 Prompt 绑定
      await updateAgentPromptBinding(role.id, {
        system_prompt_template_id: systemPromptId,
        task_prompt_template_id: taskPromptId,
        strict_json: strictJson,
        evidence_required: evidenceRequired,
      });

      onSaved?.();
      onClose();
    } catch (e: any) {
      setErrMsg(e?.message ?? String(e));
    } finally {
      setSaving(false);
    }
  };

  const handlePreview = async () => {
    setPreviewLoading(true);
    try {
      const res = await previewModelSelection(role.id, {
        selection_mode: draftMode,
        auto_strategy: draftStrategy as any,
        candidate_provider_ids: draftCandidateProviderIds,
        agent_role_key: role.key,
      });
      setPreviewData(res);
    } catch {
      setPreviewData(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  // ── 渲染 ────────────────────────────────────────────
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal agent-editor-modal"
        onClick={(e) => e.stopPropagation()}
        style={{ width: 600, maxWidth: "95vw" }}
      >
        <div className="modal-head">
          <h3 className="serif">编辑 Agent · {role.display_name}</h3>
          <button onClick={onClose} className="modal-close">&#10005;</button>
        </div>

        {/* ── Tab 切换 ─────────────────────────────────── */}
        <div style={{ display: "flex", gap: 4, padding: "8px 16px", borderBottom: "1px solid var(--border)" }}>
          {TABS.map((t) => (
            <button
              key={t}
              className={`pill ${tab === t ? "primary" : ""}`}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="modal-body">
          {errMsg && <div className="error">{errMsg}</div>}

          {/* ═══════════════ Tab 1: 基础信息 ═══════════════ */}
          {tab === "基础信息" && (
            <div className="agent-editor-grid">
              <Field label="显示名称" required>
                <input className="input" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
              </Field>
              <Field label="分类">
                <select className="input" value={category} onChange={(e) => setCategory(e.target.value as AgentCategory)}>
                  {CATEGORIES.map((c) => <option key={c} value={c}>{AGENT_CATEGORY_LABEL[c]}</option>)}
                </select>
              </Field>
              <Field label="头像样式">
                <select className="input" value={avatarStyle} onChange={(e) => setAvatarStyle(e.target.value as AgentAvatarStyle)}>
                  {AGENT_AVATAR_STYLES.map((s) => <option key={s.key} value={s.key}>{s.emoji} {s.label}</option>)}
                </select>
              </Field>
              <Field label="调度模式">
                <select className="input" value={runMode} onChange={(e) => setRunMode(e.target.value)}>
                  {RUN_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </Field>
              <Field label="流水线阶段 (可选)">
                <input className="input" value={pipelineStage} onChange={(e) => setPipelineStage(e.target.value)} placeholder="after_draft_before_critic" />
              </Field>
              <Field label="超时 (秒)">
                <input className="input" type="number" value={timeoutSeconds} onChange={(e) => setTimeoutSeconds(Number(e.target.value) || 0)} />
              </Field>
              <Field label="最大重试">
                <input className="input" type="number" value={maxRetries} onChange={(e) => setMaxRetries(Number(e.target.value) || 0)} />
              </Field>
              <Field label="并发上限">
                <input className="input" type="number" value={concurrencyLimit} onChange={(e) => setConcurrencyLimit(Number(e.target.value) || 0)} />
              </Field>
              <Field label="成本上限 (USD, 可空)">
                <input className="input" type="number" step="0.001" value={costLimit} onChange={(e) => setCostLimit(e.target.value)} />
              </Field>
              <Field label="启用">
                <label className="inline-checkbox">
                  <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
                  启用 (worker 才会调度)
                </label>
              </Field>
              <Field label="矩阵可见">
                <label className="inline-checkbox">
                  <input type="checkbox" checked={visibleInMatrix} onChange={(e) => setVisibleInMatrix(e.target.checked)} />
                  在角色绑定矩阵中显示
                </label>
              </Field>
              <Field label="职责描述" full>
                <textarea className="input" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
              </Field>
            </div>
          )}

          {/* ═══════════════ Tab 2: 模型绑定 ═══════════════ */}
          {tab === "模型绑定" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {/* 绑定模式 */}
              <div>
                <div className="muted small" style={{ marginBottom: 4 }}>绑定模式</div>
                <BindingModeSwitch value={draftMode} onChange={setDraftMode} />
              </div>

              {/* auto: 策略 + 候选 + 预览 */}
              {draftMode === "auto" && (
                <>
                  <div>
                    <div className="muted small" style={{ marginBottom: 4 }}>自动策略</div>
                    <AutoStrategySelect value={draftStrategy} onChange={setDraftStrategy} />
                  </div>
                  <div>
                    <div className="muted small" style={{ marginBottom: 4 }}>候选 Provider</div>
                    <CandidateProviderPicker
                      providerIds={draftCandidateProviderIds}
                      onChange={setDraftCandidateProviderIds}
                      providers={providers.map((p) => ({ id: p.id, name: p.name, enabled: p.enabled }))}
                    />
                  </div>
                  <div>
                    <button className="tiny primary" onClick={handlePreview} disabled={previewLoading}>
                      {previewLoading ? "预览中..." : "预览选择"}
                    </button>
                    <ModelSelectionPreviewPanel data={previewData} loading={previewLoading} />
                  </div>
                </>
              )}

              {/* manual / manual_with_fallback: provider + model 下拉 */}
              {(draftMode === "manual" || draftMode === "manual_with_fallback") && (
                <div>
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
                <div>
                  <div className="muted small" style={{ marginBottom: 4 }}>Fallback 候选</div>
                  <FallbackCandidateEditor
                    candidates={draftFallbackCandidates}
                    onChange={setDraftFallbackCandidates}
                    allowAutoFallback={draftAllowAutoFallback}
                    onAllowChange={setDraftAllowAutoFallback}
                  />
                </div>
              )}

              {/* 温度 / MaxTokens / TopP 滑块 */}
              <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12 }}>
                <div className="muted small" style={{ marginBottom: 8 }}>模型参数</div>
                <SliderRow label="Temperature" value={draftTemperature} min={0} max={2} step={0.1} onChange={setDraftTemperature} />
                <SliderRow label="Max Tokens" value={draftMaxTokens} min={256} max={128000} step={256} onChange={setDraftMaxTokens} />
                <SliderRow label="Top P" value={draftTopP} min={0} max={1} step={0.05} onChange={setDraftTopP} />
              </div>
            </div>
          )}

          {/* ═══════════════ Tab 3: Prompt 绑定 ═══════════════ */}
          {tab === "Prompt 绑定" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div>
                <div className="muted small" style={{ marginBottom: 4 }}>System Prompt 模板</div>
                <select
                  className="input"
                  value={systemPromptId ?? ""}
                  onChange={(e) => setSystemPromptId(e.target.value ? Number(e.target.value) : null)}
                >
                  <option value="">-- 未绑定 --</option>
                  {promptTemplates
                    .filter((t) => t.role === "system" || t.scope === "system")
                    .map((t) => (
                      <option key={t.id} value={t.id}>{t.name} ({t.template_key})</option>
                    ))}
                </select>
              </div>

              <div>
                <div className="muted small" style={{ marginBottom: 4 }}>Task Prompt 模板</div>
                <select
                  className="input"
                  value={taskPromptId ?? ""}
                  onChange={(e) => setTaskPromptId(e.target.value ? Number(e.target.value) : null)}
                >
                  <option value="">-- 未绑定 --</option>
                  {promptTemplates
                    .filter((t) => t.role === "task" || t.scope === "task")
                    .map((t) => (
                      <option key={t.id} value={t.id}>{t.name} ({t.template_key})</option>
                    ))}
                </select>
              </div>

              {/* 所有模板一览（按 genre 分组） */}
              <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12 }}>
                <div className="muted small" style={{ marginBottom: 8 }}>可用模板 (按类型)</div>
                <div style={{ maxHeight: 240, overflowY: "auto", fontSize: 12 }}>
                  {promptTemplates.length === 0 ? (
                    <div className="muted small">暂无模板</div>
                  ) : (
                    promptTemplates.map((t) => (
                      <div
                        key={t.id}
                        style={{
                          display: "flex", alignItems: "center", gap: 8,
                          padding: "4px 0", borderBottom: "1px solid var(--border)",
                        }}
                      >
                        <span className="pill tiny">{t.role}</span>
                        <span>{t.name}</span>
                        <span className="muted small" style={{ marginLeft: "auto" }}>
                          {t.genre ?? "通用"} · {t.category}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div>
                <label className="inline-checkbox">
                  <input type="checkbox" checked={strictJson} onChange={(e) => setStrictJson(e.target.checked)} />
                  严格 JSON 输出
                </label>
              </div>
              <div>
                <label className="inline-checkbox">
                  <input type="checkbox" checked={evidenceRequired} onChange={(e) => setEvidenceRequired(e.target.checked)} />
                  需要证据引用
                </label>
              </div>
            </div>
          )}
        </div>

        <div className="modal-foot">
          <button onClick={onClose}>取消</button>
          <button className="primary" onClick={handleSave} disabled={saving}>
            {saving ? "保存中..." : "保存全部"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── 辅助组件 ──────────────────────────────────────────────

function Field({ label, children, required, hint, full }: {
  label: string; children: React.ReactNode; required?: boolean; hint?: string; full?: boolean;
}) {
  return (
    <div className="agent-editor-field" data-full={full ? "1" : "0"}>
      <label>
        {label}
        {required && <span className="required">*</span>}
        {hint && <span className="field-hint"> · {hint}</span>}
      </label>
      {children}
    </div>
  );
}

function SliderRow({ label, value, min, max, step, onChange }: {
  label: string; value: number; min: number; max: number; step: number;
  onChange: (v: number) => void;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
      <div style={{ width: 100, fontSize: 12, color: "var(--text-secondary)" }}>{label}</div>
      <input
        type="range"
        min={min} max={max} step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ flex: 1 }}
      />
      <input
        className="input"
        type="number"
        min={min} max={max} step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ width: 72, textAlign: "right" }}
      />
    </div>
  );
}
