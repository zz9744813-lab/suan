/**
 * StudyPage (R18 rewrite) — 拆书 → 模式
 *
 * 旧的 3-section 布局 (① 材料 / ② 详情 / ③ 模式库) 改成 tab + 树状:
 *
 *   ┌─ Tab 切换 ─────────────────────────────────────────┐
 *   │  📚 我的书库    /    🧩 行为模式                    │
 *   └────────────────────────────────────────────────────┘
 *   「我的书库」tab:
 *     - 顶部 toolbar: 搜索 + 上传 (txt/md/pdf/docx/html/epub) + 粘贴新建
 *     - 主体: 书本卡片网格. 每张卡片默认折叠, 点开显示章节 → 人物
 *     - 卡片内部是树状: 章节行可点开看原文 + 抽取人物
 *   「行为模式」tab: 标签筛选 + 搜索 + 卡片列表, 跟 R16 一样
 *
 * 砍掉的"杂乱"来源: 旧的 3 段式把"创建材料"、"材料详情"和"模式库"
 * 三个独立的卡片从上到下平铺, 用户得不停滚屏 + 在两个不同的
 * "selectedId" 状态间来回. 现在先选书, 再选章节, 层次清晰.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  listStudyMaterials,
  createStudyMaterial,
  uploadStudyMaterialsBatch,
  getStudyMaterial,
  chapterizeStudyMaterial,
  runStudyChapter,
  runStudyBulk,
  deleteStudyCharacter,
  listBehaviorPatterns,
  createBehaviorPattern,
  deleteBehaviorPattern,
  deleteStudyMaterial,
  getTask,
  extractStudyBehaviors,
  getStudyMaterialOverview,
  getStudyRelationships,
  applyStudyRelationships,
  getStudyForeshadows,
} from "../api";
import type {
  StudyMaterial,
  StudyMaterialDetail,
  StudyChapter,
  StudyCharacter,
  StudyBulkPayload,
  BehaviorPattern,
  StudyMaterialOverview,
  StudyRelationshipSuggestion,
  StudyRelationshipsResponse,
  StudyForeshadowSummary,
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
  // New material form (collapsed by default — the upload button is
  // the primary path now that we accept 6 formats).
  const [showNew, setShowNew] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newAuthor, setNewAuthor] = useState("");
  const [newText, setNewText] = useState("");
  // R21: live bulk-study progress. ``bulkProgress`` is keyed by
  // material_id so the user can run a bulk on book A, expand
  // book B, and still see book A's bar ticking in the background.
  // ``bulkTimers`` holds the polling setTimeout handle so the
  // component can cancel them on unmount.
  const [bulkProgress, setBulkProgress] = useState<
    Record<number, StudyBulkPayload & { task_id: number; status: string }>
  >({});
  const bulkTimers = useRef<Record<number, ReturnType<typeof setTimeout> | null>>({});
  // R22: per-material overview cache (chapters/characters/behaviors/
  // foreshadows/graph_node_count). Refreshed after a behavior
  // extract or a graph materialise, so the badges stay honest.
  const [overviews, setOverviews] = useState<Record<number, StudyMaterialOverview>>({});
  // R22: relationships-modal state. ``relMaterialId`` opens the
  // modal with the corresponding material's suggestions. The
  // ``relationInputs`` map holds the per-suggestion free-form
  // label the user types before applying.
  const [relMaterialId, setRelMaterialId] = useState<number | null>(null);
  const [relData, setRelData] = useState<StudyRelationshipsResponse | null>(null);
  const [relLoading, setRelLoading] = useState(false);
  const [relApplyMsg, setRelApplyMsg] = useState<string | null>(null);
  const [relApplyBusy, setRelApplyBusy] = useState(false);
  // ``selectedSuggestions`` is a Set of "a_id-b_id" keys the user
  // ticked in the modal. Persists across renders so the user can
  // freely edit relation labels without losing their selection.
  const [selectedSuggestions, setSelectedSuggestions] = useState<Set<string>>(new Set());
  const [relationInputs, setRelationInputs] = useState<Record<string, string>>({});

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

  // R21: kick off a background bulk study on every chapter of one
  // book. The endpoint returns immediately with a task_id; we
  // poll ``GET /api/tasks/{id}`` every 2.5s and write the
  // counters into ``bulkProgress`` so the user sees the bar
  // tick up. When the task reaches a terminal state (succeeded /
  // failed), we refresh the book detail to pull the freshly
  // persisted characters / events.
  const onRunStudyBulk = async (
    material: StudyMaterial,
    mode: "character" | "event" | "both",
    limit: number,
  ) => {
    setErrorMsg(null);
    try {
      const start = await runStudyBulk(material.id, {
        mode,
        limit,
        max_concurrency: 3,
        force: true,
        max_chars: 4000,
      });
      setBulkProgress((prev) => ({
        ...prev,
        [material.id]: {
          task_id: start.task_id,
          material_id: material.id,
          mode,
          total_chapters: start.total_chapters,
          chapters_to_process: start.chapters_to_process,
          chapters_processed: 0,
          characters_added: 0,
          events_added: 0,
          errors: [],
          max_concurrency: 3,
          force: true,
          max_chars: 4000,
          status: "running",
        },
      }));
      // Start the polling loop for this material.
      const tick = async () => {
        try {
          const t = await getTask(start.task_id);
          const payload = (t.payload || {}) as StudyBulkPayload;
          setBulkProgress((prev) => ({
            ...prev,
            [material.id]: {
              ...payload,
              task_id: t.id,
              status: t.status,
            },
          }));
          if (t.status === "succeeded" || t.status === "failed") {
            // Terminal — refresh book detail to pick up the new
            // character_count / event_count, and stop polling.
            bulkTimers.current[material.id] = null;
            if (expanded === material.id) {
              const d = await getStudyMaterial(material.id);
              setDetail(d);
            }
            refresh();
            return;
          }
        } catch (e: any) {
          // Polling error — keep retrying unless the task is
          // already gone from the server (404 → treat as done).
          setErrorMsg(`轮询任务失败: ${e?.message ?? e}`);
        }
        const handle = setTimeout(tick, 2500);
        bulkTimers.current[material.id] = handle;
      };
      const handle = setTimeout(tick, 1500);
      bulkTimers.current[material.id] = handle;
    } catch (e: any) {
      setErrorMsg(e?.message ?? String(e));
    }
  };

  // Cancel any in-flight polling timers when the page unmounts.
  useEffect(() => {
    const timers = bulkTimers.current;
    return () => {
      for (const k of Object.keys(timers)) {
        const h = timers[Number(k)];
        if (h) clearTimeout(h);
      }
    };
  }, []);

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
  // extract-behaviors) without paying for the whole list.
  const refreshOverview = async (materialId: number) => {
    try {
      const o = await getStudyMaterialOverview(materialId);
      setOverviews((prev) => ({ ...prev, [materialId]: o }));
    } catch {
      // Ignore.
    }
  };

  // R22: kick off the behavior-pattern extraction. Synchronous
  // endpoint (one LLM call) so we just await the response and
  // refresh the overview once it's done.
  const onExtractBehaviors = async (m: StudyMaterial) => {
    setBusy(true);
    setErrorMsg(null);
    try {
      const r = await extractStudyBehaviors(m.id, {
        max_patterns: 20,
        force: false,
        max_chunk_chars: 1500,
        evidence_chapter_count: 5,
      });
      const data = r ?? null;
      const added = data?.patterns_added ?? 0;
      const skipped = data?.patterns_skipped ?? 0;
      const sample = (data?.sample_names ?? []).join("、") || "—";
      setErrorMsg(
        `提取完成: 新增 ${added} 条模式,跳过 ${skipped} 条(已存在)。示例: ${sample}。`,
      );
      await refreshOverview(m.id);
    } catch (e: any) {
      setErrorMsg(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  };

  // R22: open the relationship-modal. The endpoint is cheap
  // (just a SQL join) so we don't need a separate loading row.
  const onAnalyzeRelationships = async (m: StudyMaterial) => {
    setRelMaterialId(m.id);
    setRelData(null);
    setRelApplyMsg(null);
    setSelectedSuggestions(new Set());
    setRelationInputs({});
    setRelLoading(true);
    try {
      const r = await getStudyRelationships(m.id, { min_co_chapter_count: 1, limit: 80 });
      setRelData(r ?? null);
    } catch (e: any) {
      setErrorMsg(e?.message ?? String(e));
      setRelMaterialId(null);
    } finally {
      setRelLoading(false);
    }
  };

  // R22: apply the user-picked (pair, relation) tuples as
  // GraphEdge rows. Each picked suggestion becomes a single
  // ``{char_a_id, char_b_id, relation}`` triple. We need the
  // material's project_id to know which graph to write into;
  // if it's not set, we surface a friendly error.
  const onApplyRelationships = async (m: StudyMaterial) => {
    if (!m.project_id) {
      setRelApplyMsg("这本书还没关联到 project_id,没法写入图谱。先去编辑这本书绑定项目。");
      return;
    }
    if (!relData || selectedSuggestions.size === 0) {
      setRelApplyMsg("至少勾选一条关系再应用。");
      return;
    }
    setRelApplyBusy(true);
    setRelApplyMsg(null);
    try {
      const pairs: Array<Record<string, any>> = [];
      for (const sug of relData.suggestions) {
        const k = `${sug.char_a_id}-${sug.char_b_id}`;
        if (!selectedSuggestions.has(k)) continue;
        pairs.push({
          char_a_id: sug.char_a_id,
          char_b_id: sug.char_b_id,
          relation: (relationInputs[k] || "同章节出现").trim() || "同章节出现",
          weight: Math.min(1.0, 0.3 + 0.1 * sug.co_chapter_count),
          evidence: sug.sample_quote,
        });
      }
      const r = await applyStudyRelationships(m.id, {
        project_id: m.project_id,
        pairs,
      });
      const data = r ?? null;
      setRelApplyMsg(
        `已应用: 新增 ${data?.edges_added ?? 0} 条,跳过 ${data?.edges_skipped ?? 0} 条(已存在)。`,
      );
      setSelectedSuggestions(new Set());
      await refreshOverview(m.id);
    } catch (e: any) {
      setRelApplyMsg(e?.message ?? String(e));
    } finally {
      setRelApplyBusy(false);
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
              onRunStudyBulk={(mode, limit) => onRunStudyBulk(m, mode, limit)}
              onDeleteCharacter={onDeleteCharacter}
              bulkProgress={bulkProgress[m.id] ?? null}
              overview={overviews[m.id] ?? null}
              onExtractBehaviors={() => onExtractBehaviors(m)}
              onAnalyzeRelationships={() => onAnalyzeRelationships(m)}
            />
          ))}
        </div>
      )}

      {relMaterialId != null && (
        <RelationshipsModal
          material={materials.find((m) => m.id === relMaterialId)!}
          data={relData}
          loading={relLoading}
          selected={selectedSuggestions}
          setSelected={setSelectedSuggestions}
          relationInputs={relationInputs}
          setRelationInputs={setRelationInputs}
          applyMsg={relApplyMsg}
          applyBusy={relApplyBusy}
          onApply={() => {
            const m = materials.find((x) => x.id === relMaterialId);
            if (m) onApplyRelationships(m);
          }}
          onClose={() => setRelMaterialId(null)}
        />
      )}
    </div>
  );
}

function BookCard({
  material, expanded, detail, busy,
  onToggle, onChapterize, onDelete, onRunStudy, onRunStudyBulk, onDeleteCharacter,
  bulkProgress, overview,
  onExtractBehaviors, onAnalyzeRelationships,
}: {
  material: StudyMaterial;
  expanded: boolean;
  detail: StudyMaterialDetail | null;
  busy: boolean;
  onToggle: () => void;
  onChapterize: () => void;
  onDelete: () => void;
  onRunStudy: (ch: StudyChapter) => void;
  onRunStudyBulk: (mode: "character" | "event" | "both", limit: number) => void;
  onDeleteCharacter: (id: number) => void;
  bulkProgress: (StudyBulkPayload & { task_id: number; status: string }) | null;
  overview: StudyMaterialOverview | null;
  onExtractBehaviors: () => void;
  onAnalyzeRelationships: () => void;
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
            {/* R21: bulk action row. Two presets so the user can
                run character extraction across the WHOLE book
                (default 一次性跑完) or sample a fixed number
                of chapters first to sanity-check the model +
                token spend before committing to 2332. The
                progress bar below ticks up live from the
                polling task payload. */}
            <button
              className="primary"
              disabled={busy || !!bulkProgress || !material.chapter_count}
              onClick={() => onRunStudyBulk("character", 0)}
              title="对全书每一章都跑一次人物抽取(后台批量,可在 Dashboard 看进度)"
            >
              {bulkProgress ? "抽取中…" : "批量抽人物"}
            </button>
            <button
              disabled={busy || !!bulkProgress || !material.chapter_count || !material.project_id}
              onClick={() => onRunStudyBulk("event", 0)}
              title="对全书每一章跑一次事件抽取(伏笔/转折,需要先把这本书关联到 project_id)"
            >
              {bulkProgress ? "抽取中…" : "批量抽事件"}
            </button>
            <button
              disabled={busy || !!bulkProgress || !material.chapter_count}
              onClick={() => onRunStudyBulk("character", 5)}
              title="先跑 5 章试一下模型效果,确认 OK 再点上面跑全书"
            >
              试抽 5 章
            </button>
            {/* R22: 联动按钮 — 提取行为模式 / 分析人物关系。
                两个按钮都是同步端点,完成后刷新 overview 即可。
                「行为模式」会复用抽取过的 character roster, 所以
                在 character_count=0 时禁用,避免空跑 LLM。 */}
            <button
              disabled={busy || !material.character_count}
              onClick={onExtractBehaviors}
              title="基于已抽人物 + 章节摘要,跑一次 LLM 总结出 N 张行为模式卡"
            >
              🧩 提取行为模式
            </button>
            <button
              disabled={busy || !material.character_count}
              onClick={onAnalyzeRelationships}
              title="分析书中同章节出现的人物对,生成可一键应用到图谱的关系建议"
            >
              🔗 分析人物关系
            </button>
            <button className="danger" onClick={onDelete} disabled={busy}>
              删除
            </button>
          </div>

          {/* R22: 概览行 — 让用户一眼看到这本书"数据沉淀到了哪"。
              4 个数字 = character_count(已有) / behavior_count /
              foreshadow_count / graph_node_count。如果 overview
              还没加载完,这一行就不渲染,避免空 0 误导。 */}
          {overview && (overview.behavior_count > 0 || overview.foreshadow_count > 0 || overview.graph_node_count > 0) && (
            <div className="study-linkage-row">
              <span className="muted small">联动数据：</span>
              <span className="study-linkage-chip" title="已沉淀到行为模式库">
                🧩 行为 <b>{overview.behavior_count}</b>
              </span>
              <span className="study-linkage-chip" title="已沉淀到伏笔库(需要 project_id)">
                📜 伏笔 <b>{overview.foreshadow_count}</b>
              </span>
              <span className="study-linkage-chip" title="已导入到图谱(任何 kind)">
                🌐 图谱 <b>{overview.graph_node_count}</b>
              </span>
              {overview.graph_node_count === 0 && material.project_id && (
                <span className="muted tiny">
                  提示: 进入「图谱」页 → 选这本书导入,即可一键把人物/伏笔/行为送进图谱
                </span>
              )}
            </div>
          )}

          {/* R21: live progress bar for the in-flight bulk job on
              this book. We pull the per-chapter counters from the
              polled AgentTask.payload. Stays visible after the
              task finishes so the user can see "finished, 3 chars
              added" before they scroll the page. */}
          {bulkProgress && (
            <BulkProgressBar payload={bulkProgress} />
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

// R21: live progress bar for an in-flight bulk study job.
// Shows "已处理 X / Y" + the per-mode counters (chars added /
// events added) and a horizontal fill bar. The bar is
// percentage-based off ``chapters_processed / chapters_to_process``;
// if the backend somehow reports a denominator of 0 we fall
// through to ``0%`` (defensive — should never happen in practice).
function BulkProgressBar({
  payload,
}: {
  payload: StudyBulkPayload & { task_id: number; status: string };
}) {
  const total = Math.max(payload.chapters_to_process, 1);
  const pct = Math.min(100, Math.round((payload.chapters_processed / total) * 100));
  const isRunning = payload.status === "running" || payload.status === "pending";
  const isError = payload.status === "failed";
  const modeLabel: Record<string, string> = {
    character: "人物",
    event: "事件",
    both: "人物+事件",
  };
  return (
    <div className={`bulk-progress ${isError ? "error" : isRunning ? "running" : "done"}`} style={{ marginBottom: 10 }}>
      <div className="row" style={{ gap: 10, fontSize: 12, marginBottom: 4 }}>
        <span>
          <b>{modeLabel[payload.mode] ?? payload.mode}</b>
          {" · 已处理 "}
          <b>{payload.chapters_processed}</b> / {payload.chapters_to_process} 章
        </span>
        <span className="muted">· +{payload.characters_added} 人物 · +{payload.events_added} 事件</span>
        <span className="muted">· task #{payload.task_id}</span>
        <span className="spacer" />
        <span className={`pill tiny ${isError ? "error" : isRunning ? "warn" : "ok"}`}>{payload.status}</span>
      </div>
      <div className="bulk-progress-track">
        <div
          className="bulk-progress-fill"
          style={{ width: `${pct}%` }}
        />
      </div>
      {payload.errors && payload.errors.length > 0 && (
        <div className="muted small" style={{ marginTop: 4 }}>
          错误 {payload.errors.length} 条（仅显示前 3 条）：
          <ul style={{ margin: "4px 0 0 18px" }}>
            {payload.errors.slice(0, 3).map((e, i) => <li key={i}>{e}</li>)}
          </ul>
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

// R22: 人物关系建议模态。
// 显示每对 (char_a, char_b) 的 co_chapter_count / 最后出现章节 /
// sample_quote,用户勾选并给一个关系标签,点"应用"批量写 graph_edges。
function RelationshipsModal({
  material, data, loading, selected, setSelected,
  relationInputs, setRelationInputs,
  applyMsg, applyBusy, onApply, onClose,
}: {
  material: StudyMaterial;
  data: StudyRelationshipsResponse | null;
  loading: boolean;
  selected: Set<string>;
  setSelected: (s: Set<string>) => void;
  relationInputs: Record<string, string>;
  setRelationInputs: (r: Record<string, string>) => void;
  applyMsg: string | null;
  applyBusy: boolean;
  onApply: () => void;
  onClose: () => void;
}) {
  const toggle = (k: string) => {
    const next = new Set(selected);
    if (next.has(k)) next.delete(k);
    else next.add(k);
    setSelected(next);
  };
  const setRel = (k: string, v: string) => {
    setRelationInputs({ ...relationInputs, [k]: v });
  };
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <header>
          <h3>人物关系分析 · {material.title}</h3>
          <button onClick={onClose}>×</button>
        </header>
        <div className="modal-body">
          {loading ? (
            <div className="muted small">分析中…</div>
          ) : !data || data.suggestions.length === 0 ? (
            <div className="muted small">
              还没有可建议的关系。要么这本书还没抽过人物,要么所有人物都没有挂在具体章节上。
            </div>
          ) : (
            <>
              <p className="muted small">
                扫描了 <b>{data.chapters_scanned}</b> 章、共 <b>{data.total_characters}</b> 个有人物来源的角色,
                按"同章节出现"频次排序。勾选要写入图谱的关系,给一个标签(默认「同章节出现」),点「应用」即可。
              </p>
              <div className="rel-suggestion-list">
                {data.suggestions.map((sug) => {
                  const k = `${sug.char_a_id}-${sug.char_b_id}`;
                  const checked = selected.has(k);
                  return (
                    <div key={k} className={`rel-suggestion ${checked ? "checked" : ""}`}>
                      <label className="rel-suggestion-head">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggle(k)}
                        />
                        <span>
                          <b>{sug.char_a_name}</b> ↔ <b>{sug.char_b_name}</b>
                          <span className="muted tiny" style={{ marginLeft: 8 }}>
                            同章 {sug.co_chapter_count} 次 · 最近 第 {sug.last_chapter_no || "?"} 章
                            {sug.last_chapter_title ? ` · ${sug.last_chapter_title}` : ""}
                          </span>
                        </span>
                      </label>
                      <div className="rel-suggestion-row">
                        <input
                          placeholder="关系标签,如 师父 / 恋人 / 对手"
                          value={relationInputs[k] ?? ""}
                          onChange={(e) => setRel(k, e.target.value)}
                          disabled={!checked}
                        />
                      </div>
                      {sug.sample_quote && (
                        <div className="muted tiny rel-suggestion-quote">
                          「{sug.sample_quote.slice(0, 160)}」
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
        <footer>
          {applyMsg && <span className="muted small" style={{ marginRight: "auto" }}>{applyMsg}</span>}
          <span className="spacer" />
          <span className="muted small" style={{ marginRight: 8 }}>
            已选 {selected.size} 条
          </span>
          <button onClick={onClose}>关闭</button>
          <button
            className="primary"
            disabled={applyBusy || selected.size === 0 || !data || data.suggestions.length === 0}
            onClick={onApply}
          >
            {applyBusy ? "写入中…" : "应用到图谱"}
          </button>
        </footer>
      </div>
    </div>
  );
}

/* ===================== 行为模式库 ===================== */

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

  const refreshPatterns = () => {
    listBehaviorPatterns({
      character: charFilter ? [charFilter] : undefined,
      situation: sitFilter ? [sitFilter] : undefined,
      search: search || undefined,
    })
      .then(setPatterns)
      .catch((e) => setErrorMsg(String(e?.message ?? e)));
  };

  useEffect(refreshPatterns, [charFilter, sitFilter, search]);

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
        <div className="row" style={{ marginBottom: 8 }}>
          <h3 style={{ margin: 0 }}>行为模式库（{patterns.length}）</h3>
          <span className="spacer" />
          <button onClick={() => setShowNewPattern(!showNewPattern)}>
            {showNewPattern ? "取消" : "+ 新建模式"}
          </button>
        </div>
        <p className="muted small">
          模式按 <b>人物标签</b> × <b>情境标签</b> 检索。PlannerAgent 会把命中的模式卡注入章节规划 prompt。
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
