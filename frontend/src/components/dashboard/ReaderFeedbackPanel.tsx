/**
 * ReaderFeedbackPanel — Dashboard 右面板"读者反馈"卡片 (NF2 闭环 Step 1)
 *
 * 展示当前章节 5 位模拟读者的反馈概览：
 *   - 读者名称 + 评分
 *   - hooked / dropped / meh 状态
 *   - 关键评语（最多一条）
 *
 * 格式：
 *   Reader-A 爽点  7.8 ✅ 建议提前冲突
 *   Reader-B 逻辑  8.6 ✅ 动机成立
 *   Reader-C 人物  6.9 ⚠️ 配角存在感弱
 *   Reader-D 节奏  7.1 ⚠️ 中段拖慢
 *   Reader-E 商业  8.2 ✅ 钩子可继续
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useProjectStore } from "../../stores/projectStore";
import { listChapters, listReaderAgents, getReaderComments } from "../../api";

/** 从后端返回的 reader 记录映射到 display 信息 */
const READER_META: Record<string, { label: string; dimension: string; order: number }> = {
  reader_a: { label: "Reader-A 爽点", dimension: "爽点/钩子", order: 0 },
  reader_b: { label: "Reader-B 逻辑", dimension: "逻辑/因果", order: 1 },
  reader_c: { label: "Reader-C 人物", dimension: "人物/弧光", order: 2 },
  reader_d: { label: "Reader-D 节奏", dimension: "节奏/张弛", order: 3 },
  reader_e: { label: "Reader-E 商业", dimension: "商业/留存", order: 4 },
};

/** 每个读者一行 */
interface ReaderLine {
  key: string;
  label: string;
  dimension: string;
  score: number | null;
  sentiment: "hooked" | "dropped" | "meh" | null;
  comment: string | null;
}

function sentimentIcon(s: string | null): string {
  if (s === "hooked") return "✅";
  if (s === "dropped") return "❌";
  if (s === "meh") return "⚠️";
  return "—";
}

function sentimentColor(s: string | null): string {
  if (s === "hooked") return "var(--state-ok, #4ade80)";
  if (s === "dropped") return "var(--state-error, #f87171)";
  if (s === "meh") return "var(--state-warn, #fbbf24)";
  return "var(--text-muted)";
}

/** 从一条 reader_agent 评论里提取评分、情绪、评语 */
function parseReaderComment(c: any): { score: number | null; sentiment: "hooked" | "dropped" | "meh" | null; comment: string | null } {
  const rating = c?.rating ?? {};
  const score: number | null = typeof rating?.score === "number" ? rating.score
    : typeof rating?.overall === "number" ? rating.overall
    : null;
  const sentiment: "hooked" | "dropped" | "meh" | null =
    rating?.sentiment === "hooked" || rating?.sentiment === "dropped" || rating?.sentiment === "meh"
      ? rating.sentiment
      : null;
  const comment: string | null =
    typeof c?.content === "string" && c.content.length > 0 ? c.content.slice(0, 80) : null;
  return { score, sentiment, comment };
}

export function ReaderFeedbackPanel() {
  const projectId = useProjectStore((s) => s.currentProjectId);
  const [lines, setLines] = useState<ReaderLine[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!projectId) { setLines([]); return; }
      setLoading(true);
      try {
        // 1. 获取最新章节
        const chapters = await listChapters(projectId);
        const latestChapter = chapters.length > 0
          ? chapters.slice().sort((a, b) => b.id - a.id)[0]
          : null;

        // 2. 构建读者基线
        const initial: ReaderLine[] = Object.entries(READER_META).map(([key, meta]) => ({
          key,
          label: meta.label,
          dimension: meta.dimension,
          score: null,
          sentiment: null,
          comment: null,
        }));

        if (!latestChapter) {
          if (!cancelled) setLines(initial);
          return;
        }

        // 3. 尝试获取 Reader Agent 列表并取最新评论
        const readers = await listReaderAgents().catch(() => [] as any[]);
        const readerList = Array.isArray(readers) ? readers : (readers as any)?.items ?? [];
        const readerKeys = readerList.map((r: any) => r.reader_key);

        // 过滤出我们的 5 个 Reader
        const ourKeys = Object.keys(READER_META);
        const resolved: ReaderLine[] = [...initial];

        // 对每个 reader 拉取最新的评论
        await Promise.all(
          ourKeys.map(async (rk, idx) => {
            // 如果后端有这个 reader，拉评论；否则保持空
            if (readerKeys.includes(rk)) {
              try {
                const comments = await getReaderComments(rk, 3);
                const arr = Array.isArray(comments) ? comments : [];
                if (arr.length > 0) {
                  // 取最新的一条（已按时间倒序？假设后端已排序）
                  const latest = arr[0];
                  const { score, sentiment, comment } = parseReaderComment(latest);
                  resolved[idx] = { ...resolved[idx], score, sentiment, comment };
                }
              } catch { /* 该 reader 暂无评论 */ }
            }
          }),
        );

        // 按 order 排序
        resolved.sort((a, b) => (READER_META[a.key]?.order ?? 99) - (READER_META[b.key]?.order ?? 99));

        if (!cancelled) setLines(resolved);
      } catch { /* silent */ }
      finally { if (!cancelled) setLoading(false); }
    }
    load();
    const id = window.setInterval(load, 30000);
    return () => { cancelled = true; window.clearInterval(id); };
  }, [projectId]);

  if (!projectId) {
    return (
      <section className="card">
        <div className="card-header">
          <h3>读者反馈</h3>
          <span className="muted small">5 位模拟读者</span>
        </div>
        <div className="muted small" style={{ padding: 16 }}>
          选择一个项目后，这里会显示最近章节的读者评审反馈。
        </div>
      </section>
    );
  }

  if (loading && lines.length === 0) {
    return (
      <section className="card">
        <div className="card-header">
          <h3>读者反馈</h3>
          <span className="muted small">5 位模拟读者</span>
        </div>
        <div className="muted small" style={{ padding: 16 }}>加载中…</div>
      </section>
    );
  }

  return (
    <section className="card">
      <div className="card-header">
        <h3>读者反馈</h3>
        <span className="muted small">5 位模拟读者</span>
      </div>

      <div style={{ padding: "8px 0" }}>
        {lines.map((line) => (
          <div
            key={line.key}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "6px 18px",
              fontSize: 12,
              borderBottom: "1px solid var(--accent-line-soft, rgba(255,255,255,0.04))",
            }}
          >
            {/* 读者名称 */}
            <span style={{ color: "var(--text-primary)", fontWeight: 500, minWidth: 120 }}>
              {line.label}
            </span>

            {/* 评分 */}
            <span
              style={{
                fontWeight: 600,
                minWidth: 36,
                textAlign: "center",
                color: line.score != null
                  ? line.score >= 8 ? "var(--state-ok, #4ade80)"
                  : line.score >= 7 ? "var(--state-warn, #fbbf24)"
                  : "var(--state-error, #f87171)"
                  : "var(--text-muted)",
              }}
            >
              {line.score != null ? line.score.toFixed(1) : "—"}
            </span>

            {/* 情绪状态 */}
            <span
              style={{
                color: sentimentColor(line.sentiment),
                minWidth: 24,
                textAlign: "center",
              }}
              title={line.sentiment === "hooked" ? "上钩" : line.sentiment === "dropped" ? "弃读" : line.sentiment === "meh" ? "一般" : "无数据"}
            >
              {sentimentIcon(line.sentiment)}
            </span>

            {/* 关键评语 */}
            <span
              style={{
                color: "var(--text-secondary)",
                flex: 1,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {line.comment ?? "暂无评语"}
            </span>
          </div>
        ))}
      </div>

      {/* 底部跳转链接 */}
      <div style={{ padding: "8px 18px 12px", borderTop: "1px solid var(--accent-line)" }}>
        <Link
          to={`/projects/${projectId}/reader-agents`}
          className="muted small"
          style={{ textDecoration: "none" }}
        >
          查看全部读者评审 →
        </Link>
      </div>
    </section>
  );
}
