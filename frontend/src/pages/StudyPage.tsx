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
import { useEffect, useMemo, useState } from "react";
import {
  listStudyMaterials,
  createStudyMaterial,
  uploadStudyMaterial,
  uploadStudyMaterialsBatch,
  getStudyMaterial,
  chapterizeStudyMaterial,
  runStudyChapter,
  deleteStudyCharacter,
  listBehaviorPatterns,
  createBehaviorPattern,
  deleteBehaviorPattern,
  deleteStudyMaterial,
} from "../api";
import type {
  StudyMaterial,
  StudyMaterialDetail,
  StudyChapter,
  StudyCharacter,
  BehaviorPattern,
} from "../types";
import "./StudyPage.css";

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
    const files = Array.from(e.target.files ?? []);
    if (files.length === 0) return;
    setBusy(true);
    setErrorMsg(null);
    try {
      if (files.length === 1) {
        // Single-file path: keep the same UX (auto-expand the new book).
        const file = files[0];
        const stem = file.name.replace(/\.[^.]+$/, "");
        const m = await uploadStudyMaterial((() => {
          const fd = new FormData();
          fd.append("title", stem);
          fd.append("file", file);
          return fd;
        })());
        refresh();
        setExpanded(m.id);
      } else {
        // R19: multi-file path. Backend caps at 5 and auto-chapterizes
        // each. We surface per-file failures so a bad EPUB doesn't
        // hide a successful TXT upload next to it.
        if (files.length > 5) {
          setErrorMsg(`一次最多 5 本书,收到 ${files.length} 本,已截取前 5 本。`);
        }
        const fd = new FormData();
        for (const f of files.slice(0, 5)) {
          fd.append("files", f);
        }
        const results = await uploadStudyMaterialsBatch(fd);
        const failed = results.filter((r) => !r.ok);
        if (failed.length > 0) {
          setErrorMsg(
            `已上传 ${results.length - failed.length}/${results.length} 本;` +
            `失败: ${failed.map((f) => f.filename ?? "?").join(", ")}`,
          );
        }
        refresh();
      }
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
          {busy ? "上传中…" : `📤 上传 (${ACCEPTED_LABEL}, ≤5 本)`}
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
          <div className="row" style={{ marginBottom: 10, gap: 8 }}>
            <span className="muted small">id={material.id} · {new Date(material.created_at).toLocaleDateString()}</span>
            <span className="spacer" />
            <button onClick={onChapterize} disabled={busy || !material.raw_text_length}>
              {busy ? "分章中…" : "重新分章"}
            </button>
            <button className="danger" onClick={onDelete} disabled={busy}>
              删除
            </button>
          </div>

          {d?.error && (
            <div className="error small" style={{ marginBottom: 8 }}>
              上次分章失败: {d.error}
            </div>
          )}

          {!d ? (
            <div className="muted small">加载中…</div>
          ) : d.chapters.length === 0 ? (
            <div className="muted small">
              还没有章节。点「重新分章」自动切分正文（支持「第 N 章」和「Chapter N」两种格式）。
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
