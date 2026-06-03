/**
 * PolicyPresetsCard — WorkerPage 上的"一键套用策略预设"卡片 (Round 12)
 *
 * 设计: 不修改 WorkerPolicy 模型, 不新增后端 endpoint — 预设就是
 * 4 个硬编码的 JSON, 点一下就把这套值 PUT 到 /api/projects/{id}/policy
 * 然后刷新本地 state。够轻, 也够直观。
 *
 * 4 档:
 *   保守    — 低预算, 高门槛, 失败立刻停
 *   标准    — 默认 (跟 seed 出来的一样)
 *   激进    — 高目标, 高预算, 多重试
 *   实验    — 极宽松门槛, 关闭 auto_continue (适合手动观察)
 *
 * R16 / P0-WORKER-2: 第 5 张「自定义」卡. 用户点开后展开一个 7 字段
 * 表单, 填好点保存 → 写到 localStorage (novelforge.worker.custom.v1)
 * 同时 PUT 到 /api/projects/{id}/policy. 重启浏览器后仍能看到这张卡.
 * 没有后端改动 — 跟其他 4 张卡一样, 最终值是 PUT 到 worker_policies.
 */
import { useEffect, useState } from "react";
import { useProjectStore } from "../../stores/projectStore";
import { getPolicy, updatePolicy } from "../../api";
import type { WorkerPolicy } from "../../types";
import "./PolicyPresetsCard.css";

type Preset = {
  key: string;
  label: string;
  desc: string;
  emoji: string;
  body: Partial<WorkerPolicy>;
};

const PRESETS: Preset[] = [
  {
    key: "conservative",
    label: "保守",
    desc: "低预算 · 高门槛 · 失败立刻停",
    emoji: "🛡",
    body: {
      daily_word_goal: 15000,
      daily_budget_usd: 4.0,
      pass_score: 85,
      max_rewrite_rounds: 1,
      max_retry_per_task: 2,
      consecutive_fail_stop: 2,
      auto_continue: true,
    },
  },
  {
    key: "standard",
    label: "标准",
    desc: "默认配置, 适合大多数情况",
    emoji: "⚖",
    body: {
      daily_word_goal: 30000,
      daily_budget_usd: 8.0,
      pass_score: 80,
      max_rewrite_rounds: 2,
      max_retry_per_task: 3,
      consecutive_fail_stop: 3,
      auto_continue: true,
    },
  },
  {
    key: "aggressive",
    label: "激进",
    desc: "高目标 · 高预算 · 多重试",
    emoji: "⚡",
    body: {
      daily_word_goal: 50000,
      daily_budget_usd: 15.0,
      pass_score: 70,
      max_rewrite_rounds: 3,
      max_retry_per_task: 5,
      consecutive_fail_stop: 5,
      auto_continue: true,
    },
  },
  {
    key: "experimental",
    label: "实验",
    desc: "极宽松 · 关 auto_continue (手动观察)",
    emoji: "🧪",
    body: {
      daily_word_goal: 20000,
      daily_budget_usd: 20.0,
      pass_score: 60,
      max_rewrite_rounds: 4,
      max_retry_per_task: 8,
      consecutive_fail_stop: 8,
      auto_continue: false,
    },
  },
];

// R16: localStorage key for the user's custom preset. Bump suffix
// if we ever need to invalidate.
const CUSTOM_PRESET_KEY = "novelforge.worker.custom.v1";

type CustomPreset = {
  name: string;
  body: Partial<WorkerPolicy>;
};

function loadCustomPreset(): CustomPreset | null {
  try {
    const raw = localStorage.getItem(CUSTOM_PRESET_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || !parsed.body) return null;
    return parsed as CustomPreset;
  } catch {
    return null;
  }
}

function saveCustomPreset(p: CustomPreset) {
  localStorage.setItem(CUSTOM_PRESET_KEY, JSON.stringify(p));
}

function clearCustomPreset() {
  localStorage.removeItem(CUSTOM_PRESET_KEY);
}

function presetsDiffer(p: WorkerPolicy, body: Partial<WorkerPolicy>): boolean {
  for (const k of Object.keys(body) as (keyof WorkerPolicy)[]) {
    if ((body as any)[k] !== (p as any)[k]) return true;
  }
  return false;
}

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
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  // R16: custom preset state. Loaded once on mount. ``editing`` flips
  // to true when the user clicks the 5th card (saved or empty) to
  // bring up the inline form.
  const [custom, setCustom] = useState<CustomPreset | null>(() => loadCustomPreset());
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Partial<WorkerPolicy>>({});

  useEffect(() => {
    if (!projectId) { setPolicy(null); return; }
    getPolicy(projectId).then(setPolicy).catch(() => setPolicy(null));
  }, [projectId]);

  if (!projectId) {
    return (
      <div className="card ppc-card">
        <h3>策略预设</h3>
        <div className="muted small">选一个项目后,这里会显示该项目当前的 Worker 策略,并提供 4 套预设一键套用。</div>
      </div>
    );
  }
  if (!policy) {
    return (
      <div className="card ppc-card">
        <h3>策略预设</h3>
        <div className="muted small">正在加载项目 #{projectId} 的策略…</div>
      </div>
    );
  }

  async function apply(preset: Preset) {
    if (!projectId) return;
    if (policy && presetsDiffer(policy, preset.body)) {
      const ok = confirm(
        `应用「${preset.label}」预设?\n\n` +
        `会覆盖当前策略:\n` +
        `  每日目标: ${policy.daily_word_goal} → ${preset.body.daily_word_goal}\n` +
        `  每日预算: $${policy.daily_budget_usd} → $${preset.body.daily_budget_usd}\n` +
        `  通过分数: ${policy.pass_score} → ${preset.body.pass_score}\n` +
        `  最大改稿: ${policy.max_rewrite_rounds} → ${preset.body.max_rewrite_rounds}\n` +
        `  最大重试: ${policy.max_retry_per_task} → ${preset.body.max_retry_per_task}\n` +
        `  auto_continue: ${policy.auto_continue} → ${preset.body.auto_continue}`
      );
      if (!ok) return;
    }
    setBusy(preset.key); setMsg(null);
    try {
      const updated = await updatePolicy(projectId, preset.body);
      setPolicy(updated);
      setMsg({ type: "ok", text: `已应用「${preset.label}」预设` });
      setTimeout(() => setMsg(null), 2500);
    } catch (e: any) {
      setMsg({ type: "err", text: `保存失败: ${e.message}` });
    } finally {
      setBusy(null);
    }
  }

  // R16: open the custom editor. If a saved preset exists, prefill
  // the form with its body. Otherwise prefill from the current
  // policy so the user can tweak incrementally.
  function startEdit() {
    setDraft(custom?.body ?? policy ?? {});
    setEditing(true);
  }

  async function saveCustom() {
    if (!projectId) return;
    // Reject obviously bogus values so the worker doesn't loop at 0
    // words forever or burn the daily budget in 1 chapter.
    if (typeof draft.daily_word_goal === "number" && draft.daily_word_goal < 100) {
      setMsg({ type: "err", text: "每日目标字数不能小于 100" });
      return;
    }
    if (typeof draft.daily_budget_usd === "number" && draft.daily_budget_usd <= 0) {
      setMsg({ type: "err", text: "每日预算必须 > 0" });
      return;
    }
    setBusy("custom"); setMsg(null);
    try {
      const body = { ...policy, ...draft } as Partial<WorkerPolicy>;
      const updated = await updatePolicy(projectId, body);
      setPolicy(updated);
      const name = custom?.name ?? "自定义";
      const next: CustomPreset = { name, body: draft };
      saveCustomPreset(next);
      setCustom(next);
      setEditing(false);
      setMsg({ type: "ok", text: `已保存「${name}」自定义预设` });
      setTimeout(() => setMsg(null), 2500);
    } catch (e: any) {
      setMsg({ type: "err", text: `保存失败: ${e.message}` });
    } finally {
      setBusy(null);
    }
  }

  function deleteCustom() {
    if (!confirm("删除自定义预设?\n\n(只删本地保存,当前已应用的策略不会回退)")) return;
    clearCustomPreset();
    setCustom(null);
    setEditing(false);
    setMsg({ type: "ok", text: "已删除自定义预设" });
    setTimeout(() => setMsg(null), 2500);
  }

  const customIsCurrent = custom ? presetsDiffer(policy, custom.body) === false : false;

  return (
    <div className="card ppc-card">
      <div className="ppc-head">
        <h3>策略预设</h3>
        <span className="muted small">项目 #{projectId} · {PRESETS.length + (custom ? 1 : 0) + 1} 套一套用</span>
      </div>

      <div className="ppc-grid">
        {PRESETS.map((p) => {
          const isCurrent = !presetsDiffer(policy, p.body);
          return (
            <button
              key={p.key}
              className={`ppc-tile ${isCurrent ? "current" : ""} ${busy === p.key ? "busy" : ""}`}
              onClick={() => apply(p)}
              disabled={busy !== null}
            >
              <div className="ppc-tile-emoji">{p.emoji}</div>
              <div className="ppc-tile-name">
                {p.label}
                {isCurrent && <span className="ppc-current-tag">当前</span>}
              </div>
              <div className="ppc-tile-desc">{p.desc}</div>
              <div className="ppc-tile-stats">
                <span><b>{p.body.daily_word_goal}</b>字/日</span>
                <span><b>${p.body.daily_budget_usd}</b>/日</span>
                <span>≥ <b>{p.body.pass_score}</b>分</span>
              </div>
            </button>
          );
        })}

        {/* R16: 5th card — custom (saved or empty) */}
        {!editing && (
          <button
            className={`ppc-tile ${custom ? "" : "ppc-tile-custom-empty"} ${customIsCurrent ? "current" : ""} ${busy === "custom" ? "busy" : ""}`}
            onClick={startEdit}
            disabled={busy !== null}
            title={custom ? `已保存「${custom.name}」,点开编辑` : "点开自定义策略"}
          >
            <div className="ppc-tile-emoji">{custom ? "📝" : "＋"}</div>
            <div className="ppc-tile-name">
              {custom?.name ?? "自定义"}
              {customIsCurrent && <span className="ppc-current-tag">当前</span>}
            </div>
            <div className="ppc-tile-desc">
              {custom
                ? `已保存 · ${custom.body.daily_word_goal}字 $${custom.body.daily_budget_usd} ≥${custom.body.pass_score}分`
                : "点开设置自己的 7 字段 · 保存在本地"}
            </div>
            {custom && (
              <div className="ppc-tile-stats">
                <span><b>{custom.body.daily_word_goal}</b>字/日</span>
                <span><b>${custom.body.daily_budget_usd}</b>/日</span>
                <span>≥ <b>{custom.body.pass_score}</b>分</span>
              </div>
            )}
          </button>
        )}

        {editing && (
          <div className="ppc-edit-form">
            <div className="ppc-field" style={{ gridColumn: "1 / -1" }}>
              <label>预设名称</label>
              <input
                type="text"
                value={custom?.name ?? ""}
                placeholder="(留空则用「自定义」)"
                maxLength={20}
                onChange={(e) => setCustom((c) => ({ name: e.target.value, body: c?.body ?? draft }))}
              />
            </div>
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
              {custom && (
                <button className="danger" onClick={deleteCustom} disabled={busy !== null}>
                  删除
                </button>
              )}
              <button onClick={() => setEditing(false)} disabled={busy !== null}>
                取消
              </button>
              <button className="primary" onClick={saveCustom} disabled={busy !== null}>
                {busy === "custom" ? "保存中…" : "保存并应用"}
              </button>
            </div>
          </div>
        )}
      </div>

      {msg && (
        <div className={`ppc-msg ppc-msg-${msg.type}`}>{msg.text}</div>
      )}

      <div className="ppc-foot muted tiny">
        💡 也可到「项目 → 策略」标签页手动微调单个字段。自定义预设只保存在当前浏览器(不跨设备)。
      </div>
    </div>
  );
}
