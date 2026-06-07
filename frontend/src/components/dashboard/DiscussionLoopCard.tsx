/**
 * DiscussionLoopCard — Dashboard "讨论室留痕"卡片 (NF2 闭环 Step 2)
 *
 * 展示当前活跃讨论：
 *   - 状态指示灯（运行中/待裁决/已决定）
 *   - 参与方（Chief+Critic 等）
 *   - 7 天回收倒计时
 *   - 是否已生成 Skill（→ Skill #N）
 *
 * 格式：
 *   🔴 角色动机冲突  [Chief+Critic]  待裁决  剩余5天
 *   🟢 节奏优化建议  [Reader-D+Planner]  已决定→Skill #12  剩余3天
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useProjectStore } from "../../stores/projectStore";
import { listDiscussionThreads } from "../../api";
import type { ThreadSummary } from "../../api";

/** 状态 → 指示灯颜色 */
function statusDot(status: string): string {
  switch (status) {
    case "running":
    case "discussing":
    case "started":
      return "#f59e0b"; // amber — 运行中
    case "succeeded":
    case "decided":
    case "concluded":
      return "#4ade80"; // green — 已决定
    case "failed":
    case "conflict":
      return "#f87171"; // red — 失败/冲突
    case "pending":
    case "pending_decision":
    default:
      return "#f87171"; // red — 待裁决
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case "running":
    case "discussing":
    case "started":
      return "讨论中";
    case "succeeded":
    case "decided":
    case "concluded":
      return "已决定";
    case "failed":
    case "conflict":
      return "已失败";
    case "pending":
    case "pending_decision":
    default:
      return "待裁决";
  }
}

/** 剩余天数文案 */
function remainingLabel(sec: number | null): string {
  if (sec == null) return "";
  if (sec <= 0) return "即将回收";
  const days = Math.ceil(sec / 86400);
  if (days > 30) return `剩余${days}天`;
  return `剩余${days}天`;
}

/** 7天到期颜色 */
function recycleColor(sec: number | null): string {
  if (sec == null) return "var(--text-muted)";
  if (sec <= 0) return "var(--state-error, #f87171)";
  const days = sec / 86400;
  if (days <= 1) return "var(--state-error, #f87171)";
  if (days <= 3) return "var(--state-warn, #fbbf24)";
  return "var(--text-muted)";
}

export function DiscussionLoopCard() {
  const projectId = useProjectStore((s) => s.currentProjectId);
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!projectId) { setThreads([]); return; }
      setLoading(true);
      try {
        const res = await listDiscussionThreads({
          project_id: projectId,
          status: "active,pending,running,discussing,started,deciding",
          page_size: 10,
        });
        const items = res?.items ?? [];
        // 过滤非回收状态的分录
        const active = items.filter((t) => !t.recycled_at && t.status !== "recycled");
        if (!cancelled) setThreads(active);
      } catch { /* silent */ }
      finally { if (!cancelled) setLoading(false); }
    }
    load();
    const id = window.setInterval(load, 30000);
    return () => { cancelled = true; window.clearInterval(id); };
  }, [projectId]);

  if (!projectId) {
    return (
      <section className="dashboard-card">
        <div className="card-header">
          <h3>讨论室留痕</h3>
          <span className="muted small">讨论闭环</span>
        </div>
        <div className="muted small" style={{ padding: 16 }}>
          选择一个项目后，这里会显示最近的讨论线程及其状态。
        </div>
      </section>
    );
  }

  if (loading && threads.length === 0) {
    return (
      <section className="dashboard-card">
        <div className="card-header">
          <h3>讨论室留痕</h3>
          <span className="muted small">讨论闭环</span>
        </div>
        <div className="muted small" style={{ padding: 16 }}>加载中…</div>
      </section>
    );
  }

  if (threads.length === 0) {
    return (
      <section className="dashboard-card">
        <div className="card-header">
          <h3>讨论室留痕</h3>
          <span className="muted small">讨论闭环</span>
        </div>
        <div className="muted small" style={{ padding: 16 }}>
          当前项目暂无活跃讨论。讨论会从评论冲突或用户手动发起。
        </div>
      </section>
    );
  }

  return (
    <section className="dashboard-card">
      <div className="card-header">
        <h3>讨论室留痕</h3>
        <span className="muted small">{threads.length} 条活跃</span>
      </div>

      <div style={{ padding: "8px 0" }}>
        {threads.slice(0, 8).map((t) => (
          <div
            key={t.id}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "6px 18px",
              fontSize: 12,
              borderBottom: "1px solid var(--accent-line-soft, rgba(255,255,255,0.04))",
            }}
          >
            {/* 状态指示灯 */}
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                backgroundColor: statusDot(t.status),
                flexShrink: 0,
              }}
              title={statusLabel(t.status)}
            />

            {/* 讨论标题 */}
            <Link
              to={`/projects/${projectId}/discussion/${t.id}`}
              style={{
                color: "var(--text-primary)",
                textDecoration: "none",
                flex: 1,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                fontWeight: 500,
              }}
            >
              {t.title}
            </Link>

            {/* 参与方 */}
            <span style={{ color: "var(--text-muted)", fontSize: 10, flexShrink: 0 }}>
              [{t.source_agent_role ?? "—"}]
            </span>

            {/* 状态 / Skill */}
            <span
              style={{
                fontSize: 10,
                color: t.has_skill_draft ? "var(--accent-gold, #d4af37)" : "var(--text-muted)",
                flexShrink: 0,
              }}
            >
              {t.has_skill_draft && t.skill_draft_id != null
                ? `已决定→Skill #${t.skill_draft_id}`
                : statusLabel(t.status)}
            </span>

            {/* 回收倒计时 */}
            {t.remaining_seconds != null && t.status !== "recycled" && (
              <span
                style={{
                  fontSize: 10,
                  color: recycleColor(t.remaining_seconds),
                  flexShrink: 0,
                  minWidth: 60,
                  textAlign: "right",
                }}
              >
                {remainingLabel(t.remaining_seconds)}
              </span>
            )}
          </div>
        ))}
      </div>

      {/* 底部跳转 */}
      <div style={{ padding: "8px 18px 12px", borderTop: "1px solid var(--accent-line)" }}>
        <Link
          to={`/projects/${projectId}/discussions`}
          className="muted small"
          style={{ textDecoration: "none" }}
        >
          查看全部讨论 →
        </Link>
      </div>
    </section>
  );
}
