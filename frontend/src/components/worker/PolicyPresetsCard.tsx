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

function presetsDiffer(p: WorkerPolicy, body: Partial<WorkerPolicy>): boolean {
  for (const k of Object.keys(body) as (keyof WorkerPolicy)[]) {
    if ((body as any)[k] !== (p as any)[k]) return true;
  }
  return false;
}

export function PolicyPresetsCard() {
  const projectId = useProjectStore((s) => s.currentProjectId);
  const [policy, setPolicy] = useState<WorkerPolicy | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);

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

  return (
    <div className="card ppc-card">
      <div className="ppc-head">
        <h3>策略预设</h3>
        <span className="muted small">项目 #{projectId} · 4 套一键套用</span>
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
      </div>

      {msg && (
        <div className={`ppc-msg ppc-msg-${msg.type}`}>{msg.text}</div>
      )}

      <div className="ppc-foot muted tiny">
        💡 也可到「项目 → 策略」标签页手动微调单个字段。
      </div>
    </div>
  );
}
