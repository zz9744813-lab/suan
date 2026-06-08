/**
 * PolicyPresetsCard — Worker 自定义策略卡片
 *
 * 只保留当前项目的自定义策略编辑、保存和应用，不再提供固定预设。
 */
import { useEffect, useState } from "react";
import { useProjectStore } from "../../stores/projectStore";
import { getPolicy, updatePolicy } from "../../api";
import type { WorkerPolicy } from "../../types";
import "./PolicyPresetsCard.css";

const FIELDS: Array<{ key: keyof WorkerPolicy; label: string; type: "number" | "checkbox"; step?: number }> = [
  { key: "daily_word_goal", label: "每日目标字数", type: "number", step: 1000 },
  { key: "daily_budget_usd", label: "每日预算 ($)", type: "number", step: 0.5 },
  { key: "pass_score", label: "通过分数", type: "number", step: 1 },
  { key: "max_rewrite_rounds", label: "最大改稿轮数", type: "number", step: 1 },
  { key: "max_retry_per_task", label: "每任务最大重试", type: "number", step: 1 },
  { key: "consecutive_fail_stop", label: "连续失败停机阈值", type: "number", step: 1 },
  { key: "auto_continue", label: "auto_continue (自动续写)", type: "checkbox" },
];

export function PolicyPresetsCard() {
  const projectId = useProjectStore((s) => s.currentProjectId);
  const [policy, setPolicy] = useState<WorkerPolicy | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [draft, setDraft] = useState<Partial<WorkerPolicy>>({});

  useEffect(() => {
    if (!projectId) {
      setPolicy(null);
      setDraft({});
      return;
    }
    getPolicy(projectId)
      .then((p) => {
        setPolicy(p);
        setDraft(p);
      })
      .catch(() => {
        setPolicy(null);
        setDraft({});
      });
  }, [projectId]);

  if (!projectId) {
    return (
      <div className="card ppc-card">
        <h3>Worker 自定义策略</h3>
        <div className="muted small">请先选择项目，然后编辑该项目的 Worker 策略。</div>
      </div>
    );
  }

  if (!policy) {
    return (
      <div className="card ppc-card">
        <h3>Worker 自定义策略</h3>
        <div className="muted small">正在加载项目 #{projectId} 的策略…</div>
      </div>
    );
  }

  async function saveCustom() {
    if (!projectId) return;
    if (typeof draft.daily_word_goal === "number" && draft.daily_word_goal < 100) {
      setMsg({ type: "err", text: "每日目标字数不能小于 100" });
      return;
    }
    if (typeof draft.daily_budget_usd === "number" && draft.daily_budget_usd <= 0) {
      setMsg({ type: "err", text: "每日预算必须 > 0" });
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const updated = await updatePolicy(projectId, { ...policy, ...draft });
      setPolicy(updated);
      setDraft(updated);
      setMsg({ type: "ok", text: "自定义策略已保存并应用" });
      setTimeout(() => setMsg(null), 2500);
    } catch (e: any) {
      setMsg({ type: "err", text: `保存失败: ${e.message}` });
    } finally {
      setBusy(false);
    }
  }

  function resetDraft() {
    if (!policy) return;
    setDraft(policy);
    setMsg(null);
  }

  return (
    <div className="card ppc-card">
      <div className="ppc-head">
        <h3>Worker 自定义策略</h3>
        <span className="muted small">项目 #{projectId} · 仅保留自定义配置</span>
      </div>

      <div className="ppc-grid">
        <div className="ppc-edit-form always-open">
          {FIELDS.map((f) => (
            <div className="ppc-field" key={f.key}>
              <label>
                {f.label}
                {f.type === "checkbox" && (
                  <input
                    type="checkbox"
                    checked={Boolean((draft as any)[f.key])}
                    onChange={(e) => setDraft({ ...draft, [f.key]: e.target.checked })}
                  />
                )}
              </label>
              {f.type === "number" && (
                <input
                  type="number"
                  step={f.step}
                  value={(draft as any)[f.key] ?? 0}
                  onChange={(e) => setDraft({ ...draft, [f.key]: Number(e.target.value) })}
                />
              )}
            </div>
          ))}
          <div className="ppc-form-actions">
            <button onClick={resetDraft} disabled={busy}>恢复当前值</button>
            <button className="primary" onClick={saveCustom} disabled={busy}>
              {busy ? "保存中…" : "保存并应用"}
            </button>
          </div>
        </div>
      </div>

      {msg && <div className={`ppc-msg ppc-msg-${msg.type}`}>{msg.text}</div>}

      <div className="ppc-foot muted tiny">
        这里直接修改当前项目的 Worker 策略字段，不再提供固定策略预设。
      </div>
    </div>
  );
}
