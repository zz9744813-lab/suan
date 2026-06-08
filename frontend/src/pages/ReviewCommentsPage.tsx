/**
 * ReviewCommentsPage — 评论区驱动的模拟读者 Agent 评审系统 (P6 P5 前端)
 *
 * 3 栏布局:
 *   左 (320px)  评论流: 顶/底评论列表 + author_type / status 筛选
 *   中 (1fr)    评论详情: 内容 / 证据 / 评分 / 回复 / 切换 status
 *   右 (360px)  评论组 + 项目设置
 *
 * 关键:
 *   - 评论流数据从 /api/reviews/comments?project_id=X&include_replies=true 拉
 *   - 评论组从 /api/reviews/groups?project_id=X 拉
 *   - 项目设置从 /api/reviews/settings/{project_id} 拉
 *   - 切项目时 (currentProjectId 变) 整个页面重拉
 *   - 触发 "主 Agent 接入" (triage) 按钮 调 /api/reviews/triage
 *   - 触发 "5 个读者评审" 按钮 调 /api/reviews/runs (manual_test trigger)
 *
 * P5 这一版只接 P1 端点 (无 LLM), triage/runs 服务端会排到 P3/P2 worker.
 * 前端触发后会显示 "已入队" 提示, 跑完后下次 refresh 能看到新评论.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type {
  ReviewCommentRead,
  ReviewCommentListResponse,
  ReviewCommentGroupRead,
  ReviewSettingsRead,
} from "../types";
import { useProjectStore } from "../stores/projectStore";
import "./ReviewCommentsPage.css";

type AuthorFilter = "all" | "user" | "reader_agent" | "chief_agent" | "system";
type StatusFilter = "all" | "new" | "replied" | "grouped" | "discussing";

const SEVERITY_COLOR: Record<string, string> = {
  low: "review-side-severity-low",
  medium: "review-side-severity-medium",
  high: "review-side-severity-high",
  blocker: "review-side-severity-blocker",
};

const AUTHOR_LABEL: Record<string, string> = {
  user: "👤 用户",
  reader_agent: "🤖 读者",
  chief_agent: "🧭 主 Agent",
  system: "⚙ 系统",
};

const STATUS_LABEL: Record<string, string> = {
  new: "新",
  replied: "已回复",
  grouped: "已合并",
  discussing: "讨论中",
  accepted: "已采纳",
  rejected: "已驳回",
  ignored: "已忽略",
  done: "完成",
};

export function ReviewCommentsPage() {
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const projects = useProjectStore((s) => s.projects);
  const currentProject = useMemo(
    () => projects.find((p) => p.id === currentProjectId) ?? null,
    [projects, currentProjectId],
  );

  // 数据
  const [comments, setComments] = useState<ReviewCommentRead[]>([]);
  const [groups, setGroups] = useState<ReviewCommentGroupRead[]>([]);
  const [settings, setSettings] = useState<ReviewSettingsRead | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  // 筛选
  const [authorFilter, setAuthorFilter] = useState<AuthorFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  // UI
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [replyDraft, setReplyDraft] = useState("");

  // === 数据加载 ===
  useEffect(() => {
    if (currentProjectId) refresh();
  }, [currentProjectId]);

  async function refresh() {
    if (!currentProjectId) return;
    setError(null);
    try {
      const [c, g, s] = await Promise.all([
        api.get<ReviewCommentListResponse>(
          `/api/reviews/comments?project_id=${currentProjectId}&include_replies=true&limit=200`,
        ),
        api.get<ReviewCommentGroupRead[]>(
          `/api/reviews/groups?project_id=${currentProjectId}`,
        ),
        api.get<ReviewSettingsRead>(
          `/api/reviews/settings?project_id=${currentProjectId}`,
        ),
      ]);
      setComments(c.items);
      setGroups(g);
      setSettings(s);
    } catch (e: any) {
      setError(e.message ?? "加载失败");
    }
  }

  // === 过滤 + 排序 ===
  const filtered = useMemo(() => {
    let arr = comments.filter((c) => c.parent_id === null);
    if (authorFilter !== "all") arr = arr.filter((c) => c.author_type === authorFilter);
    if (statusFilter !== "all") arr = arr.filter((c) => c.status === statusFilter);
    return arr.sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at));
  }, [comments, authorFilter, statusFilter]);

  const selected = useMemo(
    () => comments.find((c) => c.id === selectedId) ?? null,
    [comments, selectedId],
  );
  const selectedReplies = useMemo(
    () => (selectedId ? comments.filter((c) => c.parent_id === selectedId) : []),
    [comments, selectedId],
  );

  // === 操作 ===
  async function setCommentStatus(commentId: number, status: string) {
    try {
      await api.patch(`/api/reviews/comments/${commentId}`, { status });
      await refresh();
    } catch (e: any) {
      setError(e.message ?? "改状态失败");
    }
  }

  async function postReply() {
    if (!selectedId || replyDraft.trim().length === 0) return;
    setBusy(true);
    setError(null);
    try {
      await api.post(`/api/reviews/comments/${selectedId}/reply`, {
        content: replyDraft.trim(),
      });
      setReplyDraft("");
      await refresh();
    } catch (e: any) {
      setError(e.message ?? "回复失败");
    } finally {
      setBusy(false);
    }
  }

  async function triggerTriage() {
    if (!currentProjectId) return;
    setBusy(true);
    setError(null);
    try {
      // P3 §5.4 入口: 调 chief_comment_moderator 对当前 project 全部分流
      const result = await api.post<any>(`/api/reviews/triage`, {
        project_id: currentProjectId,
        chapter_id: null,  // null = 全项目
      });
      const data = result?.data ?? result;
      const r = data.reply_count ?? 0;
      const g = data.group_count ?? 0;
      const d = data.discuss_count ?? 0;
      const i = data.ignore_count ?? 0;
      const err = data.error_count ?? 0;
      const summary = `已分流 ${data.new_comment_count ?? 0} 条: ${r}回复 · ${g}合并 · ${d}转讨论 · ${i}忽略`
        + (err ? ` · ${err} 失败` : "");
      setError(summary); // 临时用 error 槽当 toast
      await refresh();
    } catch (e: any) {
      setError(e.message ?? "触发 triage 失败");
    } finally {
      setBusy(false);
    }
  }

  async function triggerReaderReview() {
    if (!currentProjectId) return;
    setBusy(true);
    setError(null);
    try {
      // 先拿当前项目的 chapter 列表
      const listRes = await api.get<{ items: any[]; total: number } | any[]>(
        `/api/projects/${currentProjectId}/chapters`,
      );
      const chapters: any[] = Array.isArray(listRes)
        ? listRes
        : (listRes as any).items ?? [];
      const ch = chapters[0];
      // 使用 quick-generate 端点，后端会自动创建测试章节（如果没有）
      await api.post(`/api/reviews/runs/quick-generate`, {
        project_id: currentProjectId,
        chapter_id: ch?.id ?? null,
        trigger: "manual_test",
      });
      setError("✅ 已生成 5 条读者评审评论，查看左侧评论流");
      await refresh();
    } catch (e: any) {
      setError(e.message ?? "触发读者评审失败");
    } finally {
      setBusy(false);
    }
  }

  // === 渲染 ===
  if (!currentProjectId) {
    return (
      <div className="review-page">
        <div className="review-detail-empty">
          <div style={{ marginBottom: 16, fontSize: 18, fontWeight: 600 }}>
            请先选择一个项目
          </div>
          {projects.length > 0 ? (
            <>
              <div style={{ marginBottom: 8, color: "var(--fg-muted, #888)" }}>
                点击下方项目开始评审：
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6, maxWidth: 320 }}>
                {projects.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => useProjectStore.getState().selectProject(p.id)}
                    style={{
                      padding: "10px 16px",
                      border: "1px solid var(--border, #ddd)",
                      borderRadius: 6,
                      background: "var(--bg-panel, #fff)",
                      cursor: "pointer",
                      textAlign: "left",
                      fontSize: 14,
                    }}
                  >
                    <div style={{ fontWeight: 600 }}>{p.name}</div>
                    <div style={{ fontSize: 12, color: "var(--fg-muted, #888)", marginTop: 2 }}>
                      {p.genre} · 目标 {p.target_word_count?.toLocaleString() ?? 0} 字
                    </div>
                  </button>
                ))}
              </div>
            </>
          ) : (
            <div style={{ color: "var(--fg-muted, #888)" }}>
              还没有项目，请先到
              <a href="/projects" style={{ color: "var(--accent-gold, #c8a84e)", margin: "0 4px" }}>
                项目管理
              </a>
              页创建一个项目
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="review-page">
      <div className="review-topbar">
        <span className="review-topbar-title">📋 评论评审</span>
        <span className="review-topbar-stat">
          项目: {currentProject?.name ?? `#${currentProjectId}`}
        </span>
        <span className="review-topbar-stat">
          评论 {comments.length} · 组 {groups.length}
        </span>
        <span className="review-topbar-spacer" />
        <button
          className="review-topbar-btn secondary"
          onClick={triggerReaderReview}
          disabled={busy}
          title="对该项目第一章手动触发 5 个读者 Agent 评审"
        >
          🤖 5 读者评审
        </button>
        <button
          className="review-topbar-btn"
          onClick={triggerTriage}
          disabled={busy}
          title="调主 Agent 评论接入官对当前 status=new 的评论分流"
        >
          🧭 主 Agent 接入
        </button>
      </div>

      {error && <div className="review-error">{error}</div>}

      {/* 左栏: 评论流 */}
      <div className="review-list">
        <div className="review-list-filter">
          <span className="review-list-filter-label">作者</span>
          <div className="review-list-filter-row">
            {(["all", "user", "reader_agent", "chief_agent", "system"] as AuthorFilter[]).map((k) => (
              <button
                key={k}
                className={`review-list-filter-chip ${authorFilter === k ? "active" : ""}`}
                onClick={() => setAuthorFilter(k)}
              >
                {k === "all" ? "全部" : AUTHOR_LABEL[k] ?? k}
              </button>
            ))}
          </div>
          <span className="review-list-filter-label" style={{ marginTop: 4 }}>
            状态
          </span>
          <div className="review-list-filter-row">
            {(["all", "new", "replied", "grouped", "discussing"] as StatusFilter[]).map((k) => (
              <button
                key={k}
                className={`review-list-filter-chip ${statusFilter === k ? "active" : ""}`}
                onClick={() => setStatusFilter(k)}
              >
                {k === "all" ? "全部" : STATUS_LABEL[k] ?? k}
              </button>
            ))}
          </div>
        </div>

        {filtered.length === 0 ? (
          <div className="review-side-empty" style={{ padding: "20px" }}>
            还没有评论
            <br />
            <small>点上方「5 读者评审」或「主 Agent 接入」</small>
          </div>
        ) : (
          filtered.map((c) => (
            <div
              key={c.id}
              className={`review-list-item ${c.id === selectedId ? "active" : ""}`}
              onClick={() => setSelectedId(c.id)}
            >
              <div className="review-list-item-head">
                <span className="review-list-item-author">
                  {AUTHOR_LABEL[c.author_type] ?? c.author_type} · {c.author_label}
                </span>
                <span className="review-list-item-status">
                  {STATUS_LABEL[c.status] ?? c.status}
                </span>
              </div>
              <div className="review-list-item-content">{c.content}</div>
              <div className="review-list-item-meta">
                <span>权重 {c.weight_at_created.toFixed(2)}</span>
                <span>·</span>
                <span>{new Date(c.created_at).toLocaleString()}</span>
                {c.rating?.score !== undefined && (
                  <>
                    <span>·</span>
                    <span>★ {c.rating.score}</span>
                  </>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* 中栏: 详情 */}
      <div className="review-detail">
        {!selected ? (
          <div className="review-detail-empty">
            ← 选一条评论看详情
          </div>
        ) : (
          <>
            <div className="review-detail-head">
              <div>
                <div className="review-detail-author">
                  {AUTHOR_LABEL[selected.author_type]} · {selected.author_label}
                </div>
                <div className="review-detail-meta">
                  <span>#{selected.id}</span>
                  <span>·</span>
                  <span>状态: {STATUS_LABEL[selected.status] ?? selected.status}</span>
                  <span>·</span>
                  <span>{new Date(selected.created_at).toLocaleString()}</span>
                  {selected.chapter_id && (
                    <>
                      <span>·</span>
                      <span>章节 #{selected.chapter_id}</span>
                    </>
                  )}
                </div>
              </div>
              <div className="review-detail-actions">
                {selected.status === "new" && (
                  <button
                    className="review-detail-action"
                    onClick={() => setCommentStatus(selected.id, "replied")}
                  >
                    标记已回复
                  </button>
                )}
                {selected.status !== "ignored" && (
                  <button
                    className="review-detail-action"
                    onClick={() => setCommentStatus(selected.id, "ignored")}
                  >
                    忽略
                  </button>
                )}
                {selected.status !== "accepted" && (
                  <button
                    className="review-detail-action"
                    onClick={() => setCommentStatus(selected.id, "accepted")}
                  >
                    采纳
                  </button>
                )}
                {selected.status !== "rejected" && (
                  <button
                    className="review-detail-action"
                    onClick={() => setCommentStatus(selected.id, "rejected")}
                  >
                    驳回
                  </button>
                )}
              </div>
            </div>

            <div className="review-detail-content">{selected.content}</div>

            {/* 证据 */}
            {selected.evidence && selected.evidence.length > 0 && (
              <div className="review-detail-section">
                <div className="review-detail-section-title">原文证据</div>
                {selected.evidence.map((e, i) => (
                  <div key={i} className="review-detail-evidence-item">
                    「{(e as any).quote ?? JSON.stringify(e)}」
                    {(e as any).paragraph && (
                      <small style={{ color: "#888", marginLeft: 8 }}>
                        {(e as any).paragraph}
                      </small>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* 评分 */}
            {selected.rating && Object.keys(selected.rating).length > 0 && (
              <div className="review-detail-section">
                <div className="review-detail-section-title">评分</div>
                <div className="review-detail-rating">
                  {Object.entries(selected.rating).map(([k, v]) => (
                    <div key={k} className="review-detail-rating-chip">
                      <span className="review-detail-rating-chip-key">{k}</span>
                      <span className="review-detail-rating-chip-val">
                        {typeof v === "number" ? v : JSON.stringify(v)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 标签 */}
            {selected.tags && selected.tags.length > 0 && (
              <div className="review-detail-section">
                <div className="review-detail-section-title">标签</div>
                <div className="review-list-filter-row">
                  {selected.tags.map((t, i) => (
                    <span key={i} className="review-list-filter-chip active">{t}</span>
                  ))}
                </div>
              </div>
            )}

            {/* 子回复 (chief_agent / system) */}
            {selectedReplies.length > 0 && (
              <div className="review-detail-section">
                <div className="review-detail-section-title">回复 ({selectedReplies.length})</div>
                {selectedReplies.map((r) => (
                  <div key={r.id} className="review-detail-content" style={{ marginBottom: 8 }}>
                    <div className="review-detail-meta" style={{ marginBottom: 6 }}>
                      {AUTHOR_LABEL[r.author_type]} · {r.author_label} ·{" "}
                      {new Date(r.created_at).toLocaleString()}
                    </div>
                    {r.content}
                  </div>
                ))}
              </div>
            )}

            {/* 主 Agent 回复表单 */}
            <div className="review-detail-reply-form">
              <textarea
                className="review-detail-reply-textarea"
                placeholder="主 Agent 风格回复 (≤2000 字)"
                value={replyDraft}
                onChange={(e) => setReplyDraft(e.target.value)}
                maxLength={2000}
              />
              <button
                className="review-detail-reply-btn"
                onClick={postReply}
                disabled={busy || replyDraft.trim().length === 0}
              >
                提交回复
              </button>
            </div>
          </>
        )}
      </div>

      {/* 右栏: 组 + 设置 */}
      <div className="review-side">
        <div className="review-side-section">
          <div className="review-side-section-title">
            评论组 ({groups.length})
          </div>
          {groups.length === 0 ? (
            <div className="review-side-empty">还没有合并成组</div>
          ) : (
            groups.map((g) => (
              <div
                key={g.id}
                className={`review-side-group ${SEVERITY_COLOR[g.severity] ?? ""}`}
              >
                <div className="review-side-group-title">{g.title}</div>
                <div className="review-side-group-meta">
                  <span>{g.severity}</span>
                  <span>·</span>
                  <span>{g.status}</span>
                  <span>·</span>
                  <span>{g.comment_ids.length} 条</span>
                </div>
                <div style={{ fontSize: 12, marginTop: 4, color: "var(--fg-muted)" }}>
                  {g.summary}
                </div>
              </div>
            ))
          )}
        </div>

        <div className="review-side-section">
          <div className="review-side-section-title">项目设置</div>
          {settings ? (
            <>
              <div className="review-side-setting-row">
                <span>章节完成自动评审</span>
                <span>{settings.auto_reader_review ? "✓" : "—"}</span>
              </div>
              <div className="review-side-setting-row">
                <span>新评论自动分流</span>
                <span>{settings.auto_chief_triage ? "✓" : "—"}</span>
              </div>
              <div className="review-side-setting-row">
                <span>评论自动转讨论</span>
                <span>{settings.auto_discussion ? "✓" : "—"}</span>
              </div>
              <div className="review-side-setting-row">
                <span>评论保留</span>
                <span>{settings.retention_days} 天</span>
              </div>
              <div className="review-side-setting-row">
                <span>章评论上限</span>
                <span>{settings.max_comments_per_chapter}</span>
              </div>
              <div className="review-side-setting-row">
                <span>每次最多</span>
                <span>{settings.max_reader_comments_per_run} 条</span>
              </div>
              <div className="review-side-setting-row">
                <span>转讨论阈值</span>
                <span>{settings.min_severity_for_discussion}</span>
              </div>
            </>
          ) : (
            <div className="review-side-empty">无设置</div>
          )}
        </div>
      </div>
    </div>
  );
}
