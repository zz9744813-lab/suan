/**
 * SkillGeneratedCard — Dashboard "沉淀技能"卡片 (NF2 闭环 Step 3)
 *
 * 展示从讨论中沉淀的技能（Skill），每行：
 *   - 技能标题 + 类别标签
 *   - 来源讨论编号
 *   - 核心原则摘要
 *
 * 格式：
 *   📌 冲突升级节奏  [plot]  来自讨论#8  每3章一个冲突高峰
 *   📌 配角点睛法    [character]  来自讨论#12  配角每次出场推动主线
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useProjectStore } from "../../stores/projectStore";
import { listDiscussionThreads, getDiscussionThreadDetail } from "../../api";
import type { ThreadSummary, SkillDraftRead, SkillRead } from "../../api";

/** 技能类别 → 中文标签 */
function skillTypeLabel(t: string): string {
  const map: Record<string, string> = {
    plot: "剧情",
    character: "人物",
    setting: "设定",
    writing: "写作",
    rhythm: "节奏",
    commercial: "商业",
    world: "世界",
    general: "通用",
  };
  return map[t] ?? t;
}

/** 技能类别 → 颜色 */
function skillTypeColor(t: string): string {
  const map: Record<string, string> = {
    plot: "#8b5cf6",
    character: "#06b6d4",
    setting: "#ec4899",
    writing: "#f59e0b",
    rhythm: "#10b981",
    commercial: "#f97316",
    world: "#6366f1",
    general: "#6b7280",
  };
  return map[t] ?? "#6b7280";
}

/** 一条技能摘要 */
interface SkillRow {
  id: number;
  title: string;
  skillType: string;
  sourceThreadId: number | null;
  sourceThreadTitle: string | null;
  summary: string | null;
}

/** 从 SkillDraftRead 提取摘要 */
function draftRow(d: SkillDraftRead): SkillRow | null {
  const summary: string | null =
    d.source_summary ??
    d.source_thread_summary ??
    (d.execution_template ? d.execution_template.slice(0, 60) : null);
  return {
    id: d.id,
    title: d.title,
    skillType: d.skill_type,
    sourceThreadId: d.thread_id,
    sourceThreadTitle: null,
    summary,
  };
}

export function SkillGeneratedCard() {
  const projectId = useProjectStore((s) => s.currentProjectId);
  const [rows, setRows] = useState<SkillRow[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!projectId) { setRows([]); return; }
      setLoading(true);
      try {
        // 1. 拉取有 skill 的讨论线程
        const res = await listDiscussionThreads({
          project_id: projectId,
          page_size: 20,
        });
        const items: ThreadSummary[] = res?.items ?? [];

        // 过滤：has_skill_draft=true 或 skill_draft_id 不为空
        const skillThreads = items.filter(
          (t) => t.has_skill_draft || t.skill_draft_id != null,
        );

        // 2. 对每个线程拉详情获取 skill draft
        const skillRows: SkillRow[] = [];
        await Promise.all(
          skillThreads.slice(0, 10).map(async (t) => {
            try {
              const detail = await getDiscussionThreadDetail(t.id);
              const draft: SkillDraftRead | null = detail?.skill_draft ?? null;
              if (draft) {
                const row = draftRow(draft);
                if (row) {
                  row.sourceThreadTitle = t.title;
                  skillRows.push(row);
                }
              }
            } catch { /* ignore individual fetch failures */ }
          }),
        );

        // 按 id 降序（最新的在前）
        skillRows.sort((a, b) => b.id - a.id);

        if (!cancelled) setRows(skillRows);
      } catch { /* silent */ }
      finally { if (!cancelled) setLoading(false); }
    }
    load();
    const id = window.setInterval(load, 60000);
    return () => { cancelled = true; window.clearInterval(id); };
  }, [projectId]);

  if (!projectId) {
    return (
      <section className="dashboard-card">
        <div className="card-header">
          <h3>沉淀技能</h3>
          <span className="muted small">Skill 闭环</span>
        </div>
        <div className="muted small" style={{ padding: 16 }}>
          选择一个项目后，这里会显示从讨论中沉淀出来的写作技能。
        </div>
      </section>
    );
  }

  if (loading && rows.length === 0) {
    return (
      <section className="dashboard-card">
        <div className="card-header">
          <h3>沉淀技能</h3>
          <span className="muted small">Skill 闭环</span>
        </div>
        <div className="muted small" style={{ padding: 16 }}>加载中…</div>
      </section>
    );
  }

  if (rows.length === 0) {
    return (
      <section className="dashboard-card">
        <div className="card-header">
          <h3>沉淀技能</h3>
          <span className="muted small">Skill 闭环</span>
        </div>
        <div className="muted small" style={{ padding: 16 }}>
          暂无沉淀技能。完成讨论并固化为 Skill 后，技能会出现在这里。
        </div>
      </section>
    );
  }

  return (
    <section className="dashboard-card">
      <div className="card-header">
        <h3>沉淀技能</h3>
        <span className="muted small">{rows.length} 条</span>
      </div>

      <div style={{ padding: "8px 0" }}>
        {rows.slice(0, 8).map((row) => (
          <div
            key={`skill-${row.id}`}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "6px 18px",
              fontSize: 12,
              borderBottom: "1px solid var(--accent-line-soft, rgba(255,255,255,0.04))",
            }}
          >
            {/* 图钉 icon */}
            <span style={{ flexShrink: 0, fontSize: 14 }}>📌</span>

            {/* 技能标题 */}
            <span
              style={{
                color: "var(--text-primary)",
                fontWeight: 500,
                flexShrink: 0,
                minWidth: 0,
                maxWidth: 140,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {row.title}
            </span>

            {/* 类别标签 */}
            <span
              style={{
                fontSize: 10,
                color: skillTypeColor(row.skillType),
                backgroundColor: `${skillTypeColor(row.skillType)}18`,
                padding: "1px 6px",
                borderRadius: 3,
                flexShrink: 0,
              }}
            >
              [{skillTypeLabel(row.skillType)}]
            </span>

            {/* 来源讨论 */}
            {row.sourceThreadId != null && (
              <span style={{ color: "var(--text-muted)", fontSize: 10, flexShrink: 0 }}>
                来自讨论#{row.sourceThreadId}
              </span>
            )}

            {/* 原则摘要 */}
            <span
              style={{
                color: "var(--text-secondary)",
                flex: 1,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                fontSize: 11,
              }}
            >
              {row.summary ?? ""}
            </span>
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
