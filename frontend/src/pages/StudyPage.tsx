/**
 * StudyPage (P0 DeepStudy 自动联动重构)
 *
 * 旧的 "手动按钮" 模式已废弃。现在的设计原则:
 *   上传/粘贴参考书 → 启动 DeepStudy → 自动生成图谱/行为模式/技巧
 *   用户只看结果，不操作内部工序。
 *
 * 页面结构:
 *   Tab 1: 📚 我的书库 — 书卡网格, 每本书展开后显示:
 *     - 自动 DeepStudy 进度 (Run 状态/阶段/产物预览)
 *     - 章节树 (只读, 查看已抽取的人物)
 *     - "启动 DeepStudy" / "查看图谱" / "查看行为模式" / "查看技巧"
 *   Tab 2: 🧩 行为模式 — 标签筛选 + 搜索 + 卡片列表
 *
 * 已删除的手动按钮: 批量抽人物 / 批量抽事件 / 试抽5章 / 提取行为模式 /
 *   分析人物关系 / 应用关系图谱。这些是系统内部 Agent 的工作。
 *   Debug 模式下 (VITE_ENABLE_DEEPSTUDY_DEBUG=true) 仍然可见。
 */
import { useEffect, useMemo, useState } from "react";
import {
  listStudyMaterials,
  createStudyMaterial,
  uploadStudyMaterialsBatch,
  getStudyMaterial,
  chapterizeStudyMaterial,
  runStudyChapter,
  deleteStudyCharacter,
  listBehaviorPatterns,
  createBehaviorPattern,
  deleteBehaviorPattern,
  deleteStudyMaterial,
  getStudyMaterialOverview,
  startDeepStudyRun,
  getDeepStudyRun,
} from "../api";
import type {
  StudyMaterial,
  StudyMaterialDetail,
  StudyChapter,
  StudyCharacter,
  BehaviorPattern,
  StudyMaterialOverview,
} from "../types";
import "./StudyPage.css";

// R19: batch upload caps at 5 books. Frontend mirrors the backend
// cap so the user gets a clean error toast instead of a silent
// 截取 + confusion.
const MAX_BATCH_FILES = 5;

const ROLES = ["主角", "女主", "男配", "女配", "反派", "师父", "工具人", "势力代表", "其他"];
const SAMPLE_TAGS = ["公开羞辱", "宗门抛弃", "偶得异宝", "高人指点", "废柴逆袭", "日常", "危机"];

// R18 / P0-STUDY-3: frontend <input accept> mirrors the backend
// dispatch table in routers/study.py. If you add a format there,
// add it here too.
const ACCEPTED_FORMATS = ".txt,.md,.markdown,.pdf,.docx,.html,.htm,.epub";
const ACCEPTED_LABEL = "txt / md / pdf / docx / html / epub";

type Tab = "library" | "patterns";

export function StudyPage() {
  const [tab, setTab] = useState<Tab>("library");

  return (
    <div className="main-body">
      <div className="page-header">
        <div>
          <h1>拆书 · 行为模式</h1>
          <div className="sub">
            上传或粘贴参考小说 → 自动分章 → 抽取人物 → 沉淀可复用的行为模式卡。
            模式卡会被 PlannerAgent 注入章节规划 prompt。
          </div>
        </div>
      </div>

      <div className="study-tabs">
        <button
          className={`study-tab ${tab === "library" ? "active" : ""}`}
          onClick={() => setTab("library")}
        >
          📚 我的书库
        </button>
        <button
          className={`study-tab ${tab === "patterns" ? "active" : ""}`}
          onClick={() => setTab("patterns")}
        >
          🧩 行为模式
        </button>
      </div>

      {tab === "library" ? <BookLibrary /> : <PatternLibrary />}
    </div>
  );
}

/* ===================== 我的书库 (树状) ===================== */

function BookLibrary() {
  const [materials, setMaterials] = useState<StudyMaterial[]>([]);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [detail, setDetail] = useState<StudyMaterialDetail | null>(null);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  // New material form (collapsed by default)
  const [showNew, setShowNew] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newAuthor, setNewAuthor] = useState("");
  const [newText, setNewText] = useState("");
  // Per-material overview cache
  const [overviews, setOverviews] = useState<Record<number, StudyMaterialOverview>>({});
  // P0 DeepStudy: per-material run state for progress display
  const [deepstudyRuns, setDeepstudyRuns] = useState<Record<number, any>>({});
  const [deepstudyLaunchBusy, setDeepstudyLaunchBusy] = useState<Record<number, boolean>>({});

  const refresh = () => {
    listStudyMaterials()
      .then(setMaterials)
      .catch((e) => setErrorMsg(String(e?.message ?? e)));
  };

  useEffect(refresh, []);

  // When a book is expanded, fetch its full detail (chapters + chars).
  useEffect(() => {
    if (expanded == null) {
      setDetail(null);
      return;
    }
    setBusy(true);
    getStudyMaterial(expanded)
      .then(setDetail)
      .catch((e) => setErrorMsg(String(e?.message ?? e)))
      .finally(() => setBusy(false));
  }, [expanded]);

  // Re-fetch after a refresh comes back (new material created, etc).
  useEffect(() => {
    if (expanded != null) {
      getStudyMaterial(expanded).then(setDetail).catch(() => {});
    }
  }, [materials.length]);

  const filtered = useMemo(() => {
    if (!search.trim()) return materials;
    const q = search.trim().toLowerCase();
    return materials.filter(
      (m) =>
        m.title.toLowerCase().includes(q) ||
        (m.author || "").toLowerCase().includes(q),
    );
  }, [materials, search]);

  const onCreatePaste = async () => {
    if (!newTitle.trim() || !newText.trim()) {
      setErrorMsg("标题和正文都不能为空。");
      return;
    }
    setBusy(true);
    setErrorMsg(null);
    try {
      const m = await createStudyMaterial({
        title: newTitle,
        author: newAuthor,
        raw_text: newText,
        source: "paste",
      });
      setNewTitle(""); setNewAuthor(""); setNewText("");
      setShowNew(false);
      refresh();
      // Auto-expand the freshly created book so the user sees the
      // "下一步" without an extra click.
      setExpanded(m.id);
    } catch (e: any) {
      setErrorMsg(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  };

  const onUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    let files = Array.from(e.target.files ?? []);
    if (files.length === 0) return;
    // R19: enforce the 5-file cap on the client too. Anything past 5
    // is silently dropped by the browser's <input multiple> on some
    // platforms, but we want a clear signal.
    if (files.length > MAX_BATCH_FILES) {
      setErrorMsg(`一次最多 ${MAX_BATCH_FILES} 本书,收到 ${files.length} 本,已截取前 ${MAX_BATCH_FILES} 本。`);
      files = files.slice(0, MAX_BATCH_FILES);
    } else {
      setErrorMsg(null);
    }
    setBusy(true);
    try {
      // R19: single code path for both 1 and N files. The batch
      // endpoint auto-chapterizes each upload in-place, so the user
      // lands on a populated library without an extra click.
      const fd = new FormData();
      for (const f of files) fd.append("files", f);
      const results = await uploadStudyMaterialsBatch(fd);
      const failed = results.filter((r) => !r.ok);
      const ok = results.filter((r) => r.ok) as Array<{ ok: true; data: StudyMaterial }>;
      if (failed.length > 0) {
        // Surface a per-failure message but don't blow away the
        // successful uploads' visibility.
        const msgs = failed
          .map((f) => `${f.filename ?? "?"}: ${f.error}`)
          .join("\n");
        setErrorMsg(
          `已上传 ${ok.length}/${results.length} 本,失败 ${failed.length} 本:\n${msgs}`,
        );
      }
      refresh();
      // Auto-expand the first successful book so the user sees the
      // chapter tree without a second click — that's the whole
      // point of "上传后就自动拆的" (user feedback R19).
      if (ok.length > 0) setExpanded(ok[0].data.id);
    } catch (e: any) {
      setErrorMsg(e?.message ?? String(e));
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  };

  const onChapterize = async (id: number) => {
    setBusy(true);
    setErrorMsg(null);
    try {
      const d = await chapterizeStudyMaterial(id, {});
      setDetail(d);
      refresh();
    } catch (e: any) {
      setErrorMsg(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  };

  const onDeleteBook = async (m: StudyMaterial) => {
    if (!confirm(`删除「${m.title}」?\n\n该书下的章节和人物会一起被清掉。`)) return;
    setBusy(true);
    try {
      await deleteStudyMaterial(m.id);
      if (expanded === m.id) setExpanded(null);
      refresh();
    } catch (e: any) {
      setErrorMsg(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  };

  const onRunStudy = async (chapter: StudyChapter) => {
    if (!detail) return;
    setBusy(true);
    setErrorMsg(null);
    try {
      await runStudyChapter(detail.id, { chapter_id: chapter.id });
      const d = await getStudyMaterial(detail.id);
      setDetail(d);
      refresh();
    } catch (e: any) {
      setErrorMsg(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  };

  const onDeleteCharacter = async (cid: number) => {
    if (!detail) return;
    if (!confirm("删除该人物？")) return;
    await deleteStudyCharacter(detail.id, cid);
    const d = await getStudyMaterial(detail.id);
    setDetail(d);
    refresh();
  };

  // P0 DeepStudy: launch a DeepStudy run for this material
  const onLaunchDeepStudy = async (materialId: number) => {
    setDeepstudyLaunchBusy((prev) => ({ ...prev, [materialId]: true }));
    setErrorMsg(null);
    try {
      const r = await startDeepStudyRun(materialId, { mode: "full" });
      setDeepstudyRuns((prev) => ({ ...prev, [materialId]: r }));
      // Poll for updates
      pollDeepStudyRun(materialId, r.run_id);
    } catch (e: any) {
      setErrorMsg(e?.message ?? String(e));
    } finally {
      setDeepstudyLaunchBusy((prev) => ({ ...prev, [materialId]: false }));
    }
  };

  const pollDeepStudyRun = (materialId: number, runId: number) => {
    const tick = async () => {
      try {
        const r = await getDeepStudyRun(runId);
        setDeepstudyRuns((prev) => ({ ...prev, [materialId]: r }));
        if (r.status === "succeeded" || r.status === "failed" || r.status === "cancelled") {
          refresh();
          return;
        }
        setTimeout(tick, 5000);
      } catch { /* ignore */ }
    };
    setTimeout(tick, 3000);
  };

  // Load existing runs for all materials
  useEffect(() => {
    if (materials.length === 0) return;
    materials.forEach((m) => {
      // The material's study_progress may have last run info
      if ((m as any).study_progress?.last_run_id) {
        getDeepStudyRun((m as any).study_progress.last_run_id)
          .then((r) => setDeepstudyRuns((prev) => ({ ...prev, [m.id]: r })))
          .catch(() => {});
      }
    });
  }, [materials]);

  // R22: load overviews for every material in the current list so
  // the per-book 4-stat row can render the "behavior_count /
  // foreshadow_count / graph_node_count" badges without four
  // round-trips per book. Skips silently on error — the badges
  // are advisory and the row is still informative with the
  // list-endpoint's own chapter_count / character_count.
  useEffect(() => {
    if (materials.length === 0) return;
    let cancelled = false;
    (async () => {
      const next: Record<number, StudyMaterialOverview> = {};
      await Promise.all(materials.map(async (m) => {
        try {
          const o = await getStudyMaterialOverview(m.id);
          if (!cancelled) next[m.id] = o;
        } catch {
          // Ignore — overview is optional.
        }
      }));
      if (!cancelled) setOverviews(next);
    })();
    return () => { cancelled = true; };
  }, [materials]);

  // R22: re-fetch a single material's overview (e.g. after
  // DeepStudy completes) without paying for the whole list.
  const refreshOverview = async (materialId: number) => {
    try {
      const o = await getStudyMaterialOverview(materialId);
      setOverviews((prev) => ({ ...prev, [materialId]: o }));
    } catch {
      // Ignore.
    }
  };

  return (
    <div className="study-library">
      {errorMsg && (
        <div className="card error-card" role="alert">
          <div className="row">
            <b>操作失败</b>
            <span className="spacer" />
            <button onClick={() => setErrorMsg(null)}>关闭</button>
          </div>
          <pre className="error-pre">{errorMsg}</pre>
        </div>
      )}

      <div className="card study-toolbar">
        <input
          className="study-search"
          placeholder="搜索书名 / 作者"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <label className="study-upload-btn">
          <input
            type="file"
            accept={ACCEPTED_FORMATS}
            multiple
            onChange={onUpload}
            style={{ display: "none" }}
          />
          {busy ? "上传中…" : `📤 上传 (${ACCEPTED_LABEL}, ≤${MAX_BATCH_FILES} 本 · 自动分章)`}
        </label>
        <button
          className={showNew ? "" : "primary"}
          onClick={() => setShowNew(!showNew)}
        >
          {showNew ? "取消粘贴" : "📝 粘贴新建"}
        </button>
        <span className="spacer" />
        <span className="muted small">共 {materials.length} 本</span>
      </div>

      {showNew && (
        <div className="card study-new-form">
          <div className="grid-2">
            <div>
              <label>标题</label>
              <input
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="《xxx》"
              />
            </div>
            <div>
              <label>作者</label>
              <input
                value={newAuthor}
                onChange={(e) => setNewAuthor(e.target.value)}
                placeholder="可选"
              />
            </div>
          </div>
          <label>正文（粘贴到这里）</label>
          <textarea
            rows={6}
            value={newText}
            onChange={(e) => setNewText(e.target.value)}
            placeholder="第一章 起点&#10;……"
          />
          <div className="row" style={{ marginTop: 10, gap: 8 }}>
            <span className="spacer" />
            <button onClick={() => setShowNew(false)}>取消</button>
            <button className="primary" onClick={onCreatePaste} disabled={busy}>
              {busy ? "提交中…" : "保存"}
            </button>
          </div>
        </div>
      )}

      {filtered.length === 0 ? (
        <div className="card study-empty">
          <div className="study-empty-icon">📚</div>
          <div className="study-empty-title">
            {materials.length === 0
              ? "还没有拆书材料"
              : "没有匹配的书"}
          </div>
          <div className="muted small">
            {materials.length === 0
              ? "上传一个文件 (txt / md / pdf / docx / html / epub), 或者直接粘贴正文。"
              : "试试别的关键词。"}
          </div>
        </div>
      ) : (
        <div className="study-book-list">
          {filtered.map((m) => (
            <BookCard
              key={m.id}
              material={m}
              expanded={expanded === m.id}
              detail={detail}
              busy={busy}
              onToggle={() => setExpanded(expanded === m.id ? null : m.id)}
              onChapterize={() => onChapterize(m.id)}
              onDelete={() => onDeleteBook(m)}
              onRunStudy={onRunStudy}
              onDeleteCharacter={onDeleteCharacter}
              overview={overviews[m.id] ?? null}
              onLaunchDeepStudy={() => onLaunchDeepStudy(m.id)}
              deepstudyRun={deepstudyRuns[m.id] ?? null}
              launchBusy={!!deepstudyLaunchBusy[m.id]}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function BookCard({
  material, expanded, detail, busy,
  onToggle, onChapterize, onDelete, onRunStudy, onDeleteCharacter,
  overview, onLaunchDeepStudy, deepstudyRun, launchBusy,
}: {
  material: StudyMaterial;
  expanded: boolean;
  detail: StudyMaterialDetail | null;
  busy: boolean;
  onToggle: () => void;
  onChapterize: () => void;
  onDelete: () => void;
  onRunStudy: (ch: StudyChapter) => void;
  onDeleteCharacter: (id: number) => void;
  overview: StudyMaterialOverview | null;
  onLaunchDeepStudy: () => void;
  deepstudyRun: any | null;
  launchBusy: boolean;
}) {
  // The detail fetch belongs to the EXPANDED book only; if this
  // card isn't the active one, we just show the summary fields
  // from the list row.
  const isThis = expanded;
  const d = isThis ? detail : null;
  const [openChapter, setOpenChapter] = useState<number | null>(null);

  return (
    <div className={`card study-book ${isThis ? "expanded" : ""}`}>
      <button className="study-book-head" onClick={onToggle}>
        <span className="study-book-toggle">{isThis ? "▼" : "▶"}</span>
        <span className="study-book-title">
          <b>{material.title}</b>
          {material.author && (
            <span className="muted small" style={{ marginLeft: 6 }}>
              · {material.author}
            </span>
          )}
        </span>
        <span className="study-book-stats">
          <span className="study-stat">
            <b>{material.chapter_count}</b>
            <span className="muted tiny">章</span>
          </span>
          <span className="study-stat">
            <b>{material.character_count}</b>
            <span className="muted tiny">人物</span>
          </span>
          <span className="study-stat">
            <b>{(material.raw_text_length / 1000).toFixed(1)}k</b>
            <span className="muted tiny">字</span>
          </span>
          <span className={`pill tiny ${material.status === "ready" ? "ok" : material.status === "failed" ? "error" : "warn"}`}>
            {material.status}
          </span>
        </span>
      </button>

      {isThis && (
        <div className="study-book-body">
          <div className="row" style={{ marginBottom: 10, gap: 8, flexWrap: "wrap" }}>
            <span className="muted small">id={material.id} · {new Date(material.created_at).toLocaleDateString()}</span>
            <span className="spacer" />
            <button onClick={onChapterize} disabled={busy || !material.raw_text_length} title="重新按「第 N 章 / Chapter N」切分正文">
              {busy ? "分章中…" : "重新分章"}
            </button>
            {/* P0 DeepStudy: 一键启动自动流水线 */}
            <button
              className="primary"
              disabled={busy || launchBusy || !material.chapter_count || (deepstudyRun && deepstudyRun.status === "running")}
              onClick={onLaunchDeepStudy}
              title="启动 DeepStudy 自动流水线: 分章 → 实体抽取 → 事件抽取 → 关系分析 → 伏笔 → 行为模式 → 写作技巧 → 图谱生成 → 知识索引"
            >
              {launchBusy ? "启动中…"
                : deepstudyRun && deepstudyRun.status === "running" ? "运行中…"
                : deepstudyRun && deepstudyRun.status === "succeeded" ? "✅ DeepStudy 已完成"
                : "🚀 启动 DeepStudy"}
            </button>
            {material.project_id && deepstudyRun && deepstudyRun.status === "succeeded" && (
              <button
                className="link small"
                onClick={() => window.open(`/study/books/${material.id}/graph`, "_blank")}
                title="查看自动生成的知识图谱"
              >
                🌐 查看图谱
              </button>
            )}
            <button className="danger" onClick={onDelete} disabled={busy}>
              删除
            </button>
          </div>

          {/* P0 DeepStudy: 自动进度展示 */}
          {deepstudyRun && (
            <DeepStudyProgressCard run={deepstudyRun} material={material} overview={overview} />
          )}

          {/* 概览行 — 展示自动联动的产物统计 */}
          {overview && (overview.behavior_count > 0 || overview.foreshadow_count > 0 || overview.graph_node_count > 0) && (
            <div className="study-linkage-row">
              <span className="muted small">自动产物：</span>
              {overview.behavior_count > 0 && (
                <span className="study-linkage-chip" title="DeepStudy 自动沉淀的行为模式">
                  🧩 行为模式 <b>{overview.behavior_count}</b>
                </span>
              )}
              {overview.foreshadow_count > 0 && (
                <span className="study-linkage-chip" title="DeepStudy 自动分析的伏笔链路">
                  📜 伏笔 <b>{overview.foreshadow_count}</b>
                </span>
              )}
              {overview.graph_node_count > 0 && (
                <span className="study-linkage-chip" title="DeepStudy 自动生成的图谱节点">
                  🌐 图谱 <b>{overview.graph_node_count}</b> 节点
                </span>
              )}
            </div>
          )}

          {d?.error && (
            <div className="error small" style={{ marginBottom: 8 }}>
              上次分章失败: {d.error}
            </div>
          )}

          {!d ? (
            <div className="muted small">加载中…</div>
          ) : d.chapters.length === 0 ? (
            <div className="row" style={{ gap: 8, alignItems: "center" }}>
              <span className="muted small">
                还没有章节。点「自动分章」切分正文（支持「第 N 章」和「Chapter N」）。
              </span>
              <button onClick={onChapterize} disabled={busy || !material.raw_text_length}>
                {busy ? "分章中…" : "自动分章"}
              </button>
            </div>
          ) : (
            <ChapterTree
              chapters={d.chapters}
              characters={d.characters}
              openChapter={openChapter}
              setOpenChapter={setOpenChapter}
              onRunStudy={onRunStudy}
              onDeleteCharacter={onDeleteCharacter}
              busy={busy}
            />
          )}
        </div>
      )}
    </div>
  );
}

function ChapterTree({
  chapters, characters, openChapter, setOpenChapter, onRunStudy, onDeleteCharacter, busy,
}: {
  chapters: StudyChapter[];
  characters: StudyCharacter[];
  openChapter: number | null;
  setOpenChapter: (id: number | null) => void;
  onRunStudy: (ch: StudyChapter) => void;
  onDeleteCharacter: (id: number) => void;
  busy: boolean;
}) {
  // Group characters by source_chapter_id so a chapter's "已抽取" can
  // show the names right there instead of jumping to a separate tab.
  const byChapter = useMemo(() => {
    const m = new Map<number, StudyCharacter[]>();
    for (const c of characters) {
      if (c.source_chapter_id == null) continue;
      const list = m.get(c.source_chapter_id) ?? [];
      list.push(c);
      m.set(c.source_chapter_id, list);
    }
    return m;
  }, [characters]);

  return (
    <div className="study-chapter-tree">
      {chapters.map((ch) => {
        const isOpen = openChapter === ch.id;
        const chars = byChapter.get(ch.id) ?? [];
        return (
          <div key={ch.id} className={`study-chapter ${isOpen ? "open" : ""}`}>
            <div className="study-chapter-row">
              <button
                className="study-chapter-toggle"
                onClick={() => setOpenChapter(isOpen ? null : ch.id)}
                title={isOpen ? "收起" : "展开"}
              >
                {isOpen ? "▼" : "▶"}
              </button>
              <span className="study-chapter-title">
                [{ch.chapter_index}] {ch.title || "未命名"}
              </span>
              <span className="muted tiny" style={{ marginLeft: 8 }}>
                {ch.char_count} 字
                {ch.last_studied_at
                  ? ` · 已抽取 ${new Date(ch.last_studied_at).toLocaleString()}`
                  : ""}
              </span>
              <span className="spacer" />
              {chars.length > 0 && (
                <span className="muted tiny">
                  {chars.length} 个人物
                </span>
              )}
              <button onClick={() => onRunStudy(ch)} disabled={busy}>
                {busy ? "抽取中…" : ch.last_studied_at ? "重新抽取" : "抽取人物"}
              </button>
            </div>

            {isOpen && (
              <div className="study-chapter-body">
                {chars.length > 0 && (
                  <div className="study-chapter-chars">
                    <div className="muted tiny" style={{ marginBottom: 4 }}>
                      本章人物
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                      {chars.map((c) => (
                        <span
                          key={c.id}
                          className="study-char-pill"
                          title={`${c.role}${c.tags?.length ? " · " + c.tags.join(", ") : ""}`}
                        >
                          <b>{c.name}</b>
                          <span className="muted tiny">·{c.role}</span>
                          <button
                            className="study-char-del"
                            onClick={() => onDeleteCharacter(c.id)}
                            title="删除"
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                <div className="muted tiny" style={{ marginTop: 8, marginBottom: 4 }}>
                  正文
                </div>
                <pre className="study-chapter-text">{ch.content}</pre>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ===================== DeepStudy 自动进度卡片 ===================== */

function DeepStudyProgressCard({ run, material, overview }: { run: any; material: StudyMaterial; overview: StudyMaterialOverview | null }) {
  const stageLabels: Record<string, string> = {
    chapterize: "分章", chapter_profile: "章节画像", entity_extract: "实体抽取",
    event_extract: "事件抽取", scene_beat_extract: "场景节拍", relationship_analyze: "关系分析",
    foreshadow_analyze: "伏笔分析", behavior_pattern_mine: "行为模式", technique_mine: "写作技巧",
    graph_finalize: "图谱整理", study_critic: "质量审查", knowledge_index: "知识索引",
    writing_context_sync: "同步写作系统",
  };
  const statusPill = run.status === "running" ? "warn" : run.status === "succeeded" ? "ok" : run.status === "failed" ? "error" : "";
  const allStages = Object.keys(stageLabels);
  const completedStages = run.progress?.completed_stages ?? [];
  const stageIndex = completedStages.length;

  return (
    <div className="card" style={{ background: "var(--bg-elevated)", marginBottom: 10, fontSize: 12 }}>
      <div className="row" style={{ marginBottom: 6, gap: 8 }}>
        <b>DeepStudy Run #{run.id}</b>
        <span className={`pill tiny ${statusPill}`}>{run.status}</span>
        {run.status === "running" && <span className="muted tiny">当前: {stageLabels[run.current_stage] ?? run.current_stage}</span>}
        <span className="spacer" />
        {run.cost_usd > 0 && <span className="muted tiny">${run.cost_usd.toFixed(4)}</span>}
        {run.total_chapters > 0 && <span className="muted tiny">{run.processed_chapters}/{run.total_chapters} 章</span>}
      </div>

      {/* 阶段进度条 */}
      <div style={{ display: "flex", gap: 2, marginBottom: 6 }}>
        {allStages.map((s, i) => {
          const done = completedStages.includes(s) || i < stageIndex;
          const running = run.status === "running" && i === stageIndex;
          return (
            <div
              key={s}
              title={`${stageLabels[s]} ${done ? "✅" : running ? "⏳" : ""}`}
              style={{
                flex: 1, height: 6, borderRadius: 3,
                background: done ? "var(--accent)" : running ? "var(--warning)" : "var(--border)",
                opacity: done || running ? 1 : 0.4,
              }}
            />
          );
        })}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 4 }}>
        <span className="muted tiny">人物: {material.character_count}</span>
        {overview && <span className="muted tiny">行为: {overview.behavior_count} · 伏笔: {overview.foreshadow_count} · 图谱: {overview.graph_node_count}</span>}
      </div>
      {run.error && <div className="error small">{run.error}</div>}
    </div>
  );
}

/* ===================== 行为模式库 (B1 unified: behavior_cards) ===================== */

function PatternLibrary() {
  const [patterns, setPatterns] = useState<BehaviorPattern[]>([]);
  const [charFilter, setCharFilter] = useState("");
  const [sitFilter, setSitFilter] = useState("");
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [showNewPattern, setShowNewPattern] = useState(false);
  const [npName, setNpName] = useState("");
  const [npChars, setNpChars] = useState("");
  const [npSits, setNpSits] = useState("");
  const [npBehavior, setNpBehavior] = useState("");
  const [npConfidence, setNpConfidence] = useState(0.5);
  // B1: data source picker
  const [dataSource, setDataSource] = useState<"all" | "cards" | "legacy">("all");

  const refreshPatterns = () => {
    listBehaviorPatterns({
      character: charFilter ? [charFilter] : undefined,
      situation: sitFilter ? [sitFilter] : undefined,
      search: search || undefined,
      source: dataSource,
    })
      .then(setPatterns)
      .catch((e) => setErrorMsg(String(e?.message ?? e)));
  };

  useEffect(refreshPatterns, [charFilter, sitFilter, search, dataSource]);

  const allCharTags = useMemo(
    () => Array.from(new Set(patterns.flatMap((p) => p.character_tags))).sort(),
    [patterns],
  );
  const allSitTags = useMemo(
    () => Array.from(new Set(patterns.flatMap((p) => p.situation_tags))).sort(),
    [patterns],
  );

  const onCreatePattern = async () => {
    if (!npName.trim()) {
      setErrorMsg("模式名称不能为空。");
      return;
    }
    setBusy(true);
    try {
      await createBehaviorPattern({
        name: npName,
        character_tags: npChars.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
        situation_tags: npSits.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
        typical_behavior: npBehavior.split(/\n+/).map((s) => s.trim()).filter(Boolean),
        confidence: npConfidence,
      });
      setNpName(""); setNpChars(""); setNpSits(""); setNpBehavior(""); setNpConfidence(0.5);
      setShowNewPattern(false);
      refreshPatterns();
    } catch (e: any) {
      setErrorMsg(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  };

  const onDeletePattern = async (id: number) => {
    if (!confirm("删除该行为模式？")) return;
    await deleteBehaviorPattern(id);
    refreshPatterns();
  };

  return (
    <div className="study-patterns">
      {errorMsg && (
        <div className="card error-card" role="alert">
          <div className="row">
            <b>操作失败</b>
            <span className="spacer" />
            <button onClick={() => setErrorMsg(null)}>关闭</button>
          </div>
          <pre className="error-pre">{errorMsg}</pre>
        </div>
      )}

      <div className="card">
        {/* B1: unified system banner */}
        <div className="banner info" style={{ marginBottom: 12, padding: "8px 12px", background: "var(--bg-elevated)", borderRadius: 6, borderLeft: "3px solid var(--accent)", fontSize: 12 }}>
          <b>B1 统一行为模式系统</b> — 数据已合并到 <code>behavior_cards</code> 表。
          旧 <code>behavior_patterns</code> 表保留兼容性查询（运行迁移脚本后可安全废弃）。
          当前数据源: <b>{dataSource === "all" ? "全部 (cards + legacy)" : dataSource === "cards" ? "行为卡 (cards)" : "仅旧表 (legacy)"}</b>
        </div>

        <div className="row" style={{ marginBottom: 8 }}>
          <h3 style={{ margin: 0 }}>行为模式库（{patterns.length}）</h3>
          <span className="spacer" />
          <select
            value={dataSource}
            onChange={(e) => setDataSource(e.target.value as "all" | "cards" | "legacy")}
            style={{ fontSize: 12, marginRight: 8 }}
          >
            <option value="all">全部数据源</option>
            <option value="cards">行为卡 (cards)</option>
            <option value="legacy">旧表 (legacy)</option>
          </select>
          <button onClick={() => setShowNewPattern(!showNewPattern)}>
            {showNewPattern ? "取消" : "+ 新建模式"}
          </button>
        </div>
        <p className="muted small">
          B1 统一系统 — 模式按 <b>人物标签</b> × <b>情境标签</b> 检索。PlannerAgent 会把命中的模式卡注入章节规划 prompt。
        </p>

        <div className="row" style={{ gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          <select value={charFilter} onChange={(e) => setCharFilter(e.target.value)}>
            <option value="">— 全部人物 —</option>
            {allCharTags.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <select value={sitFilter} onChange={(e) => setSitFilter(e.target.value)}>
            <option value="">— 全部情境 —</option>
            {allSitTags.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <input
            placeholder="搜索 (name / typical_behavior)"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ flex: 1, minWidth: 200 }}
          />
        </div>

        {showNewPattern && (
          <div className="card" style={{ background: "var(--bg-elevated)", marginBottom: 12 }}>
            <div className="grid-2">
              <div>
                <label>模式名</label>
                <input value={npName} onChange={(e) => setNpName(e.target.value)} placeholder="逆境觉醒" />
              </div>
              <div>
                <label>置信度（0..1）</label>
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={npConfidence}
                  onChange={(e) => setNpConfidence(Number(e.target.value))}
                />
              </div>
            </div>
            <label>人物标签（逗号分隔）</label>
            <input value={npChars} onChange={(e) => setNpChars(e.target.value)} placeholder="主角, 热血" />
            <label>情境标签（逗号分隔）</label>
            <input value={npSits} onChange={(e) => setNpSits(e.target.value)} placeholder="公开羞辱, 宗门抛弃" />
            <label>典型行为（每行一条）</label>
            <textarea rows={3} value={npBehavior} onChange={(e) => setNpBehavior(e.target.value)} placeholder="沉默承受&#10;暗中发誓" />
            <div className="row" style={{ marginTop: 8 }}>
              <span className="spacer" />
              <button onClick={() => setShowNewPattern(false)}>取消</button>
              <button className="primary" onClick={onCreatePattern} disabled={busy}>保存</button>
            </div>
          </div>
        )}

        {patterns.length === 0 ? (
          <div className="muted small">还没有匹配的模式。试着调整筛选条件或新建一个。</div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))", gap: 12 }}>
            {patterns.map((p) => (
              <PatternCard key={p.id} pattern={p} onDelete={() => onDeletePattern(p.id)} />
            ))}
          </div>
        )}

        <details style={{ marginTop: 16 }}>
          <summary className="muted small">常用标签参考（{ROLES.length + SAMPLE_TAGS.length} 个）</summary>
          <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 4 }}>
            {ROLES.map((t) => <span key={t} className="pill tiny" title="角色">{t}</span>)}
            {SAMPLE_TAGS.map((t) => <span key={t} className="pill tiny" title="情境">{t}</span>)}
          </div>
        </details>
      </div>
    </div>
  );
}

function PatternCard({ pattern, onDelete }: { pattern: BehaviorPattern; onDelete: () => void }) {
  return (
    <div className="card" style={{ background: "var(--bg-elevated)" }}>
      <div className="row">
        <b>{pattern.name}</b>
        <span className="spacer" />
        <span className="muted tiny" title="置信度">{(pattern.confidence * 100).toFixed(0)}%</span>
      </div>
      <div style={{ marginTop: 6, display: "flex", flexWrap: "wrap", gap: 4 }}>
        {pattern.character_tags.map((t) => <span key={t} className="pill tiny">{t}</span>)}
        {pattern.situation_tags.map((t) => <span key={t} className="pill tiny warn">{t}</span>)}
      </div>
      {pattern.typical_behavior.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <div className="muted tiny">典型行为</div>
          <ul style={{ margin: "4px 0 0 18px", padding: 0, fontSize: 12 }}>
            {pattern.typical_behavior.map((b, i) => <li key={i}>{b}</li>)}
          </ul>
        </div>
      )}
      {pattern.evidence.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <div className="muted tiny">证据</div>
          <ul style={{ margin: "4px 0 0 18px", padding: 0, fontSize: 12 }}>
            {pattern.evidence.map((b, i) => <li key={i} className="muted">{b}</li>)}
          </ul>
        </div>
      )}
      <div className="row" style={{ marginTop: 8 }}>
        <span className="muted tiny">
          {pattern.source_material_id ? `拆自 material #${pattern.source_material_id}` : "手工创建"}
        </span>
        <span className="spacer" />
        <button className="link small" onClick={onDelete}>删除</button>
      </div>
    </div>
  );
}
