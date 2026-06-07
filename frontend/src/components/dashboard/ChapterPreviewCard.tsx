/**
 * ChapterPreviewCard — Round 3 (P1-UI-5).
 *
 * Shows the most recent chapter content (final, or last rewrite, or
 * draft) for the project the user is currently looking at. Lazy-
 * loaded so the dashboard doesn't block on chapter data when there
 * is no chapter yet.
 *
 * Layout:
 *   ┌─ 第 N 章 · 标题 ──────── 分数 / 字数 ─┐
 *   │  [前 600 字 preview]                │
 *   │  [查看完整 →]                       │
 *   └────────────────────────────────────┘
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useProjectStore } from "../../stores/projectStore";
import { getChapter, listChapters, getLatestVersion } from "../../api";
import type { Chapter, ChapterVersion } from "../../types";
import "./ChapterPreviewCard.css";

export function ChapterPreviewCard() {
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [version, setVersion] = useState<ChapterVersion | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!currentProjectId) { setChapter(null); setVersion(null); return; }
      setLoading(true);
      try {
        const chapters = await listChapters(currentProjectId);
        if (cancelled) return;
        // Most recent by id (highest = newest).
        const recent = chapters.length > 0
          ? chapters.slice().sort((a, b) => b.id - a.id)[0]
          : null;
        setChapter(recent);
        if (recent) {
          // Try "final" first, then "rewrite_2", "rewrite_1", "draft".
          const tries = ["final", "rewrite_2", "rewrite_1", "draft"];
          for (const kind of tries) {
            try {
              const v = await getLatestVersion(recent.id, kind);
              if (v && v.content) {
                if (!cancelled) setVersion(v);
                return;
              }
            } catch { /* try next */ }
          }
        }
      } catch { /* ignore */ }
      finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [currentProjectId]);

  if (!currentProjectId) return null;
  if (loading && !chapter) {
    return (
      <section className="dashboard-card preview-card">
        <div className="card-header"><h3>当前章节预览</h3></div>
        <div className="preview-loading muted small">加载中…</div>
      </section>
    );
  }
  if (!chapter) {
    return (
      <section className="dashboard-card preview-card">
        <div className="card-header"><h3>当前章节预览</h3></div>
        <div className="muted small preview-empty">还没有章节。先在项目里添加章节，然后启动流水线。</div>
      </section>
    );
  }

  const preview = (version?.content ?? "").slice(0, 600);
  return (
    <section className="dashboard-card preview-card">
      <div className="card-header">
        <h3>当前章节预览</h3>
        <Link to={`/projects/${currentProjectId}/chapters/${chapter.id}`} className="muted small">
          查看完整 →
        </Link>
      </div>
      <div className="preview-headline">
        <Link to={`/projects/${currentProjectId}/chapters/${chapter.id}`} className="preview-title gold">
          第 {chapter.chapter_no} 章 · {chapter.title}
        </Link>
        <span className="spacer" />
        <span className="muted small">
          {version ? `${version.version_kind} · ${version.content.length}字` : "暂无版本"}
          {version?.score != null && ` · ${version.score}分`}
        </span>
      </div>
      {preview ? (
        <pre className="preview-body">{preview}{preview.length >= 600 ? "…" : ""}</pre>
      ) : (
        <div className="muted small">该章节还没有正文（可能流水线未跑完）。</div>
      )}
    </section>
  );
}
