import { useEffect, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import {
  getChapter,
  listChapterVersions,
  listChapterSteps,
  getLatestVersion,
  taskEvents,
  taskSteps,
  createTask,
  workerStart,
  listReviewComments,
  quickGenerateReaderReview,
  triggerReviewTriage,
  updateReviewComment,
} from "../api";
import type { Chapter, ChapterVersion, AgentStep, ReviewCommentRead } from "../types";
import { useProjectStore } from "../stores/projectStore";
import { ChapterCompare } from "../components/chapter/ChapterCompare";
import { ShelfBreadcrumb } from "../components/shelf";
import "../components/chapter/ChapterCompare.css";

const TABS = [
  { key: "manuscript", label: "正文" },
  { key: "reader",     label: "读者" },
  { key: "compare",    label: "对比" },
  { key: "versions",   label: "版本" },
  { key: "timeline",   label: "时间线" },
  { key: "context",    label: "上下文" },
];

export function ChapterDetail() {
  const { pid, cid } = useParams();
  const projectId = Number(pid);
  const chapterId = Number(cid);
  const navigate = useNavigate();
  const selectProject = useProjectStore((s) => s.selectProject);
  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [versions, setVersions] = useState<ChapterVersion[]>([]);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [activeVersion, setActiveVersion] = useState<ChapterVersion | null>(null);
  const [tab, setTab] = useState<"manuscript" | "reader" | "compare" | "versions" | "timeline" | "context">("manuscript");
  const [busy, setBusy] = useState(false);
  const [readerBusy, setReaderBusy] = useState(false);
  const [comments, setComments] = useState<ReviewCommentRead[]>([]);
  const [readerError, setReaderError] = useState<string | null>(null);

  useEffect(() => {
    selectProject(projectId);
    const load = () => {
      getChapter(chapterId).then(setChapter).catch(() => navigate(`/projects/${projectId}`));
      listChapterVersions(chapterId).then(setVersions).catch(() => {});
      listChapterSteps(chapterId).then((data: any[]) => {
        setSteps(data as AgentStep[]);
      }).catch(() => {});
      getLatestVersion(chapterId, "final").then(setActiveVersion).catch(() => {
        getLatestVersion(chapterId, "draft").then(setActiveVersion).catch(() => {});
      });
      listReviewComments({ project_id: projectId, chapter_id: chapterId, limit: 80 })
        .then((data) => setComments(data.items || []))
        .catch(() => {});
    };
    load();
    const t = window.setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, 12000);
    return () => window.clearInterval(t);
  }, [chapterId, projectId, selectProject, navigate]);

  const onReprocess = async () => {
    setBusy(true);
    try {
      await createTask({
        project_id: projectId, chapter_id: chapterId,
        task_type: "chapter_pipeline", priority: 100, payload: { mode: "full" },
      });
      await workerStart();
    } catch (e: any) { alert(e.message); }
    finally { setBusy(false); }
  };

  const reloadComments = async () => {
    const data = await listReviewComments({ project_id: projectId, chapter_id: chapterId, limit: 80 });
    setComments(data.items || []);
  };

  const onGenerateReaderReview = async () => {
    setReaderBusy(true);
    setReaderError(null);
    try {
      const data = await quickGenerateReaderReview({
        project_id: projectId,
        chapter_id: chapterId,
        chapter_version_id: activeVersion?.id ?? null,
        trigger: "manual_test",
      });
      setComments((prev) => [...data.comments, ...prev]);
      setTab("reader");
    } catch (e: any) {
      setReaderError(e.message ?? String(e));
    } finally {
      setReaderBusy(false);
    }
  };

  const onUpdateCommentStatus = async (comment: ReviewCommentRead, status: ReviewCommentRead["status"]) => {
    setReaderBusy(true);
    setReaderError(null);
    try {
      const updated = await updateReviewComment(comment.id, { status });
      setComments((prev) => prev.map((item) => item.id === updated.id ? updated : item));
    } catch (e: any) {
      setReaderError(e.message ?? String(e));
    } finally {
      setReaderBusy(false);
    }
  };

  const onTriageComments = async () => {
    setReaderBusy(true);
    setReaderError(null);
    try {
      await triggerReviewTriage({ project_id: projectId, chapter_id: chapterId, limit: 20 });
      await reloadComments();
    } catch (e: any) {
      setReaderError(e.message ?? String(e));
    } finally {
      setReaderBusy(false);
    }
  };

  if (!chapter) return <div className="page-empty"><span className="spinner" /> 加载章节…</div>;

  const contentText = activeVersion?.content ?? "(本章还没有任何版本)";
  const words = contentText.length;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <ShelfBreadcrumb
        backTo={`/projects/${projectId}`}
        backLabel="返回项目工作台"
        items={[
          { label: "项目书架", to: "/projects" },
          { label: `项目 #${projectId}`, to: `/projects/${projectId}` },
          { label: `第 ${chapter.chapter_no} 章 · ${chapter.title}` },
          { label: TABS.find((t) => t.key === tab)?.label ?? "" },
        ]}
      />
      <div className="subheader">
        <Link to={`/projects/${projectId}`} className="muted">← 返回项目</Link>
        <h2 className="serif">第 {chapter.chapter_no} 章 · {chapter.title}</h2>
        <span className={`pill ${chapter.status}`}>{chapter.status}</span>
        {chapter.current_score != null && (
          <span className={`score-pill ${scoreClass(chapter.current_score)}`}>{chapter.current_score}</span>
        )}
        <span className="meta">{words.toLocaleString()} 字 · 目标 {chapter.target_word_count.toLocaleString()}</span>
        <div className="actions">
          <button onClick={onGenerateReaderReview} disabled={readerBusy}>
            {readerBusy ? "读者评审中…" : "发起读者评审"}
          </button>
          <button onClick={onReprocess} disabled={busy}>
            {busy ? "排入中…" : "重新跑流水线"}
          </button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateRows: "auto 1fr", flex: 1, minHeight: 0 }}>
        <div className="tabs" style={{ padding: "0 24px" }}>
          {TABS.map((t) => (
            <button key={t.key} className={`tab ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key as any)}>
              {t.label}
            </button>
          ))}
        </div>

        <div style={{ overflow: "auto", padding: "0 24px 24px" }}>
          {tab === "manuscript" && (
            <div>
              <div className="muted small" style={{ marginBottom: 8 }}>
                {activeVersion ? `显示：${activeVersion.version_kind} v${activeVersion.version_no}` : "尚无版本"}
              </div>
              <div className="manuscript">{contentText}</div>
            </div>
          )}

          {tab === "reader" && (
            <ReaderReviewPanel
              comments={comments}
              busy={readerBusy}
              error={readerError}
              onGenerate={onGenerateReaderReview}
              onTriage={onTriageComments}
              onAccept={(comment) => onUpdateCommentStatus(comment, "accepted")}
              onReject={(comment) => onUpdateCommentStatus(comment, "rejected")}
              onRefresh={reloadComments}
            />
          )}

          {tab === "compare" && <ChapterCompare versions={versions} />}

          {tab === "versions" && (
            <div className="grid-2">
              {versions.map(v => (
                <div key={v.id} className="card">
                  <div className="card-header">
                    <strong>{v.version_kind} v{v.version_no}</strong>
                    {v.score != null && <span className={`score-pill ${scoreClass(v.score)}`}>{v.score}</span>}
                  </div>
                  <p className="muted small">{new Date(v.created_at).toLocaleString()}</p>
                  {v.summary && <p>{v.summary}</p>}
                  <details>
                    <summary>查看全文</summary>
                    <pre className="manuscript" style={{ maxHeight: 480, overflow: "auto" }}>{v.content}</pre>
                  </details>
                </div>
              ))}
            </div>
          )}

          {tab === "timeline" && <Timeline chapterId={chapterId} />}
          {tab === "context" && (
            <div className="grid-2">
              <ContextPane chapterId={chapterId} />
              <div className="card">
                <h3>版本注释 (ContextCompiler 上下文快照)</h3>
                {activeVersion?.notes ? (
                  <pre className="mono tiny" style={{
                    background: "var(--bg-rail)",
                    padding: 12, borderRadius: 4,
                    maxHeight: 480, overflow: "auto",
                    whiteSpace: "pre-wrap",
                  }}>{JSON.stringify(activeVersion.notes, null, 2)}</pre>
                ) : <div className="muted">没有上下文快照。</div>}
              </div>
              <div className="card">
                <h3>提示词模板</h3>
                {steps.length === 0 ? (
                  <div className="muted">没有 step 记录。</div>
                ) : (
                  steps.map((s) => (
                    <details key={s.id} style={{ marginBottom: 8 }}>
                      <summary className="mono small">
                        {s.agent_name} · 模板 #{s.prompt_template_id} v{s.prompt_version}
                      </summary>
                      <pre style={{
                        background: "var(--bg-rail)",
                        padding: 10, borderRadius: 4,
                        maxHeight: 320, overflow: "auto",
                        whiteSpace: "pre-wrap", fontSize: 11,
                      }}>{s.input_prompt ?? "(无)"}</pre>
                    </details>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ReaderReviewPanel({
  comments,
  busy,
  error,
  onGenerate,
  onTriage,
  onAccept,
  onReject,
  onRefresh,
}: {
  comments: ReviewCommentRead[];
  busy: boolean;
  error: string | null;
  onGenerate: () => void;
  onTriage: () => void;
  onAccept: (comment: ReviewCommentRead) => void;
  onReject: (comment: ReviewCommentRead) => void;
  onRefresh: () => void;
}) {
  const active = comments.filter((comment) => comment.status !== "ignored" && comment.status !== "done");
  return (
    <div className="reader-review-grid">
      <section className="card reader-review-hero">
        <div>
          <div className="muted tiny">Reader Review</div>
          <h3>读者评审</h3>
          <p className="muted small">生成五类读者反馈后，可以直接采纳、驳回，或交给评论分流器进入讨论/改写流程。</p>
        </div>
        <div className="row">
          <button className="primary" disabled={busy} onClick={onGenerate}>{busy ? "生成中…" : "生成五维反馈"}</button>
          <button disabled={busy || comments.length === 0} onClick={onTriage}>转分流</button>
          <button disabled={busy} onClick={onRefresh}>刷新</button>
        </div>
        {error && <div className="error small">{error}</div>}
      </section>

      {active.length === 0 ? (
        <div className="page-empty card" style={{ minHeight: 280 }}>
          <div className="big">还没有读者反馈</div>
          <div className="muted">点击“生成五维反馈”，系统会从钩子、情绪、逻辑、商业、毒点五个角度给出意见。</div>
        </div>
      ) : (
        <div className="reader-comment-list">
          {active.map((comment) => (
            <article key={comment.id} className={`card reader-comment-card status-${comment.status}`}>
              <div className="card-header">
                <div>
                  <strong>{comment.author_label}</strong>
                  <div className="muted tiny">优先级 {comment.priority} · {comment.status}</div>
                </div>
                <span className="score-pill">{comment.rating?.score ?? "-"}</span>
              </div>
              <p className="reader-comment-content">{comment.content}</p>
              <div className="row" style={{ flexWrap: "wrap" }}>
                {comment.tags.map((tag) => <span key={tag} className="pill">{tag}</span>)}
              </div>
              <div className="row between" style={{ marginTop: 12 }}>
                <span className="muted tiny">{new Date(comment.created_at).toLocaleString()}</span>
                <div className="row">
                  <button disabled={busy || comment.status === "accepted"} onClick={() => onAccept(comment)}>采纳</button>
                  <button disabled={busy || comment.status === "rejected"} onClick={() => onReject(comment)}>驳回</button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function Timeline({ chapterId }: { chapterId: number }) {
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => {
    let mounted = true;
    Promise.all([
      taskEvents(chapterId).catch(() => []),
      taskSteps(chapterId).catch(() => []),
    ]).then(([events, taskStepRows]) => {
      if (!mounted) return;
      const merged = [
        ...(Array.isArray(events) ? events.map((item: any) => ({ type: "event", ...item })) : []),
        ...(Array.isArray(taskStepRows) ? taskStepRows.map((item: any) => ({ type: "step", ...item })) : []),
      ].sort((a: any, b: any) => String(b.created_at || b.timestamp || "").localeCompare(String(a.created_at || a.timestamp || "")));
      setItems(merged);
    });
    return () => { mounted = false; };
  }, [chapterId]);

  if (items.length === 0) return <div className="page-empty card">暂无时间线记录。</div>;
  return (
    <div className="timeline-list">
      {items.slice(0, 120).map((item, idx) => (
        <div key={`${item.type}-${item.id ?? idx}`} className="card">
          <div className="card-header">
            <strong>{item.title || item.event_type || item.step_key || item.type}</strong>
            <span className="muted tiny">{item.created_at || item.timestamp || ""}</span>
          </div>
          <pre className="mono tiny" style={{ whiteSpace: "pre-wrap", maxHeight: 220, overflow: "auto" }}>
            {JSON.stringify(item, null, 2)}
          </pre>
        </div>
      ))}
    </div>
  );
}

function ContextPane({ chapterId }: { chapterId: number }) {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    let mounted = true;
    listChapterSteps(chapterId).then((data: any[]) => {
      if (mounted) setRows(data || []);
    }).catch(() => {
      if (mounted) setRows([]);
    });
    return () => { mounted = false; };
  }, [chapterId]);

  return (
    <div className="card">
      <h3>章节上下文</h3>
      {rows.length > 0 ? (
        <pre className="mono tiny" style={{ whiteSpace: "pre-wrap", maxHeight: 620, overflow: "auto" }}>
          {JSON.stringify(rows.slice(0, 8), null, 2)}
        </pre>
      ) : <div className="muted">暂无上下文记录。</div>}
    </div>
  );
}

function scoreClass(s: number) {
  if (s >= 80) return "pass";
  if (s >= 60) return "fail";
  return "low";
}
