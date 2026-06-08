/**
 * AgentRoleEditor — 新增 / 编辑 Agent 的弹窗 (P4 §7.2)
 *
 * 用 modal 模式, 包含 spec §7.2 的全部字段:
 *   key, display_name, description, category, avatar_style, enabled,
 *   visible_in_matrix, run_mode, pipeline_stage, timeout_seconds,
 *   max_retries, concurrency_limit, cost_limit_usd
 *
 * 模型绑定 / prompt 绑定走单独端点, 这个弹窗只做角色基础信息.
 */
import { useEffect, useState } from "react";
import {
  AGENT_AVATAR_STYLES,
  AGENT_CATEGORY_LABEL,
  type AgentAvatarStyle,
  type AgentCategory,
  type AgentRole,
  type AgentRoleCreateBody,
  type AgentRoleUpdateBody,
  type AgentRunMode,
} from "../../types";

const CATEGORIES: AgentCategory[] = ["writing", "memory", "study", "discussion", "review", "custom"];
const RUN_MODES: AgentRunMode[] = ["manual", "pipeline", "scheduled", "event"];

export function AgentRoleEditor({
  open, mode, initial, onClose, onSave,
}: {
  open: boolean;
  mode: "create" | "edit";
  initial: AgentRole | null;
  onClose: () => void;
  onSave: (body: AgentRoleCreateBody | AgentRoleUpdateBody) => Promise<void>;
}) {
  const [key, setKey] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState<AgentCategory>("writing");
  const [avatarStyle, setAvatarStyle] = useState<AgentAvatarStyle>("scribe");
  const [enabled, setEnabled] = useState(true);
  const [visibleInMatrix, setVisibleInMatrix] = useState(true);
  const [runMode, setRunMode] = useState<AgentRunMode>("pipeline");
  const [pipelineStage, setPipelineStage] = useState("");
  const [timeoutSeconds, setTimeoutSeconds] = useState(120);
  const [maxRetries, setMaxRetries] = useState(2);
  const [concurrencyLimit, setConcurrencyLimit] = useState(1);
  const [costLimit, setCostLimit] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setErrMsg(null);
    if (mode === "edit" && initial) {
      setKey(initial.key);
      setDisplayName(initial.display_name);
      setDescription(initial.description ?? "");
      setCategory(initial.category);
      setAvatarStyle((initial.avatar_style ?? "scribe") as AgentAvatarStyle);
      setEnabled(initial.enabled);
      setVisibleInMatrix(initial.visible_in_matrix);
      setRunMode(initial.run_mode);
      setPipelineStage(initial.pipeline_stage ?? "");
      setTimeoutSeconds(initial.timeout_seconds);
      setMaxRetries(initial.max_retries);
      setConcurrencyLimit(initial.concurrency_limit);
      setCostLimit(initial.cost_limit_usd != null ? String(initial.cost_limit_usd) : "");
    } else {
      setKey("");
      setDisplayName("");
      setDescription("");
      setCategory("writing");
      setAvatarStyle("scribe");
      setEnabled(true);
      setVisibleInMatrix(true);
      setRunMode("pipeline");
      setPipelineStage("");
      setTimeoutSeconds(120);
      setMaxRetries(2);
      setConcurrencyLimit(1);
      setCostLimit("");
    }
  }, [open, mode, initial]);

  if (!open) return null;

  const submit = async () => {
    setErrMsg(null);
    if (mode === "create" && (!key.trim() || !displayName.trim())) {
      setErrMsg("key 和 display_name 必填");
      return;
    }
    if (mode === "edit" && !displayName.trim()) {
      setErrMsg("display_name 必填");
      return;
    }
    setSaving(true);
    try {
      const body: any = {
        display_name: displayName,
        description: description || null,
        category,
        avatar_style: avatarStyle,
        enabled,
        visible_in_matrix: visibleInMatrix,
        run_mode: runMode,
        pipeline_stage: pipelineStage || null,
        timeout_seconds: timeoutSeconds,
        max_retries: maxRetries,
        concurrency_limit: concurrencyLimit,
        cost_limit_usd: costLimit ? Number(costLimit) : null,
      };
      if (mode === "create") body.key = key;
      await onSave(body);
    } catch (e: any) {
      setErrMsg(e?.message ?? String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal agent-editor-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3 className="serif">{mode === "create" ? "新增 Agent" : `编辑 Agent · ${initial?.display_name ?? ""}`}</h3>
          <button onClick={onClose} className="modal-close">✕</button>
        </div>
        <div className="modal-body">
          {errMsg && <div className="error">{errMsg}</div>}
          <div className="agent-editor-grid">
            <Field label="key" required hint="稳定字符串 (a-z_0-9), 创建后不可改">
              <input
                className="input"
                value={key}
                disabled={mode === "edit"}
                onChange={(e) => setKey(e.target.value)}
                placeholder="foreshadow_inspector"
              />
            </Field>
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
              <select className="input" value={runMode} onChange={(e) => setRunMode(e.target.value as AgentRunMode)}>
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
        </div>
        <div className="modal-foot">
          <button onClick={onClose}>取消</button>
          <button className="primary" onClick={submit} disabled={saving}>
            {saving ? "保存中..." : mode === "create" ? "创建" : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children, required, hint, full }: { label: string; children: React.ReactNode; required?: boolean; hint?: string; full?: boolean }) {
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
