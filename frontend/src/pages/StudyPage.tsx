/**
 * Round 5: Study (拆书) page — 3-in-1 workbench:
 *
 *   ┌─ Section A: Materials ────────────────────────────┐
 *   │  Paste text / upload .txt  → create material      │
 *   │  List of materials with chapter / char counts     │
 *   └────────────────────────────────────────────────────┘
 *   ┌─ Section B: Material Detail (when one is selected) ┐
 *   │  Tabs: Chapters | Characters                       │
 *   │  Chapterize button (auto-split by headers)        │
 *   │  Per-chapter "Run study" button (LLM extraction)   │
 *   └────────────────────────────────────────────────────┘
 *   ┌─ Section C: Behavior Patterns ─────────────────────┐
 *   │  Tag-driven query (character / situation / search) │
 *   │  Pattern cards with evidence + delete             │
 *   └────────────────────────────────────────────────────┘
 *
 * The Study MVP uses a deterministic regex-based stub for
 * character extraction (P1-3 limitation: the prompt library ships
 * study_character but the route is wired for swap-in once a model
 * picker is in place).
 */
import { useEffect, useMemo, useState } from "react";
import {
  listStudyMaterials,
  createStudyMaterial,
  uploadStudyMaterial,
  getStudyMaterial,
  chapterizeStudyMaterial,
  runStudyChapter,
  listStudyCharacters,
  deleteStudyCharacter,
  listBehaviorPatterns,
  createBehaviorPattern,
  deleteBehaviorPattern,
} from "../api";
import type {
  StudyMaterial,
  StudyMaterialDetail,
  StudyChapter,
  StudyCharacter,
  BehaviorPattern,
} from "../types";

const ROLES = ["主角", "女主", "男配", "女配", "反派", "师父", "工具人", "势力代表", "其他"];
const SAMPLE_TAGS = ["公开羞辱", "宗门抛弃", "偶得异宝", "高人指点", "废柴逆袭", "日常", "危机"];

export function StudyPage() {
  const [materials, setMaterials] = useState<StudyMaterial[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<StudyMaterialDetail | null>(null);
  const [tab, setTab] = useState<"chapters" | "characters">("chapters");
  const [busy, setBusy] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // New material form
  const [newTitle, setNewTitle] = useState("");
  const [newAuthor, setNewAuthor] = useState("");
  const [newText, setNewText] = useState("");

  // Behavior patterns state
  const [patterns, setPatterns] = useState<BehaviorPattern[]>([]);
  const [charFilter, setCharFilter] = useState("");
  const [sitFilter, setSitFilter] = useState("");
  const [search, setSearch] = useState("");

  // New pattern form (collapsed by default)
  const [showNewPattern, setShowNewPattern] = useState(false);
  const [npName, setNpName] = useState("");
  const [npChars, setNpChars] = useState("");
  const [npSits, setNpSits] = useState("");
  const [npBehavior, setNpBehavior] = useState("");
  const [npConfidence, setNpConfidence] = useState(0.5);

  const refresh = () => {
    listStudyMaterials().then(setMaterials).catch((e) => setErrorMsg(String(e?.message ?? e)));
  };

  useEffect(refresh, []);

  useEffect(() => {
    if (selectedId == null) {
      setDetail(null);
      return;
    }
    getStudyMaterial(selectedId).then(setDetail).catch((e) => setErrorMsg(String(e?.message ?? e)));
  }, [selectedId, materials.length]);

  const refreshPatterns = () => {
    listBehaviorPatterns({
      character: charFilter ? [charFilter] : undefined,
      situation: sitFilter ? [sitFilter] : undefined,
      search: search || undefined,
    }).then(setPatterns).catch((e) => setErrorMsg(String(e?.message ?? e)));
  };

  useEffect(refreshPatterns, [charFilter, sitFilter, search]);

  const onCreatePaste = async () => {
    if (!newTitle.trim() || !newText.trim()) {
      setErrorMsg("标题和正文都不能为空。");
      return;
    }
    setBusy(true);
    setErrorMsg(null);
    try {
      await createStudyMaterial({ title: newTitle, author: newAuthor, raw_text: newText, source: "paste" });
      setNewTitle(""); setNewAuthor(""); setNewText("");
      refresh();
    } catch (e: any) {
      setErrorMsg(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  };

  const onUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setErrorMsg(null);
    try {
      const fd = new FormData();
      fd.append("title", file.name.replace(/\.txt$/i, ""));
      fd.append("file", file);
      await uploadStudyMaterial(fd);
      refresh();
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

  const onRunStudy = async (chapter: StudyChapter) => {
    if (!detail) return;
    setBusy(true);
    setErrorMsg(null);
    try {
      await runStudyChapter(detail.id, { chapter_id: chapter.id });
      // Refresh detail
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

  // Tag suggestions for the filter (union of all tags across loaded patterns).
  const allCharTags = useMemo(
    () => Array.from(new Set(patterns.flatMap((p) => p.character_tags))).sort(),
    [patterns],
  );
  const allSitTags = useMemo(
    () => Array.from(new Set(patterns.flatMap((p) => p.situation_tags))).sort(),
    [patterns],
  );

  return (
    <div className="main-body">
      <div className="page-header">
        <div>
          <h1>拆书 · 行为模式</h1>
          <div className="sub">
            粘贴或上传参考小说 → 自动分章 → 抽取人物 → 沉淀可复用的行为模式卡。
            模式卡会被 PlannerAgent 注入章节规划 prompt。
          </div>
        </div>
      </div>

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

      {/* ================== Section A: Materials ================== */}
      <div className="card">
        <h3>① 拆书材料</h3>
        <p className="muted small">粘贴正文，或上传一个 .txt 文件。文件大小不限（路由层一次性读入 raw_text）。</p>
        <div className="grid-2">
          <div>
            <label>标题</label>
            <input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="《xxx》" />
          </div>
          <div>
            <label>作者</label>
            <input value={newAuthor} onChange={(e) => setNewAuthor(e.target.value)} placeholder="可选" />
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
          <button className="primary" onClick={onCreatePaste} disabled={busy}>
            {busy ? "提交中…" : "新建并保存"}
          </button>
          <span className="muted small">或</span>
          <label className="link small" style={{ cursor: "pointer" }}>
            <input type="file" accept=".txt" onChange={onUpload} style={{ display: "none" }} />
            上传 .txt 文件
          </label>
        </div>

        <h4 style={{ marginTop: 18 }}>材料列表（{materials.length}）</h4>
        {materials.length === 0 ? (
          <div className="muted small">还没有材料。在上方粘一些正文试试。</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>标题</th>
                <th>作者</th>
                <th>状态</th>
                <th>章节</th>
                <th>人物</th>
                <th>字数</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {materials.map((m) => (
                <tr key={m.id} className={selectedId === m.id ? "selected" : ""}>
                  <td><b>{m.title}</b><div className="muted tiny">id={m.id} · {new Date(m.created_at).toLocaleDateString()}</div></td>
                  <td className="muted small">{m.author || "—"}</td>
                  <td><span className={`pill tiny ${m.status === "ready" ? "ok" : m.status === "failed" ? "error" : "warn"}`}>{m.status}</span></td>
                  <td>{m.chapter_count}</td>
                  <td>{m.character_count}</td>
                  <td className="muted small">{(m.raw_text_length / 1000).toFixed(1)}k</td>
                  <td>
                    <button onClick={() => setSelectedId(m.id)}>查看</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* ================== Section B: Material Detail ================== */}
      {detail && (
        <div className="card">
          <div className="row" style={{ marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>② 材料详情 · {detail.title}</h3>
            <span className="spacer" />
            <button onClick={() => onChapterize(detail.id)} disabled={busy || !detail.raw_text}>
              {busy ? "分章中…" : "重新分章"}
            </button>
            <button onClick={() => setSelectedId(null)}>关闭</button>
          </div>
          {detail.error && <div className="error small" style={{ marginBottom: 8 }}>上次分章失败：{detail.error}</div>}

          <div className="row" style={{ gap: 4, marginBottom: 12 }}>
            <button className={tab === "chapters" ? "primary" : ""} onClick={() => setTab("chapters")}>
              章节（{detail.chapter_count}）
            </button>
            <button className={tab === "characters" ? "primary" : ""} onClick={() => setTab("characters")}>
              人物（{detail.character_count}）
            </button>
          </div>

          {tab === "chapters" ? (
            detail.chapters.length === 0 ? (
              <div className="muted small">还没有章节。点击「重新分章」自动切分正文（支持「第 N 章」和「Chapter N」两种格式）。</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {detail.chapters.map((ch) => (
                  <ChapterRow
                    key={ch.id}
                    chapter={ch}
                    busy={busy}
                    onRunStudy={() => onRunStudy(ch)}
                  />
                ))}
              </div>
            )
          ) : (
            detail.characters.length === 0 ? (
              <div className="muted small">还没有人物。切到「章节」标签，对单章点「抽取人物」。</div>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>姓名</th>
                    <th>角色</th>
                    <th>别名</th>
                    <th>标签</th>
                    <th>来源章节</th>
                    <th>置信度</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {detail.characters.map((c) => (
                    <tr key={c.id}>
                      <td><b>{c.name}</b></td>
                      <td>{c.role}</td>
                      <td className="muted small">{(c.aliases || []).join(", ") || "—"}</td>
                      <td>
                        {(c.tags || []).map((t) => <span key={t} className="pill tiny" style={{ marginRight: 4 }}>{t}</span>)}
                      </td>
                      <td className="muted small">{c.source_chapter_id ? `ch #${c.source_chapter_id}` : "—"}</td>
                      <td>{(c.confidence * 100).toFixed(0)}%</td>
                      <td>
                        <button className="link small" onClick={() => onDeleteCharacter(c.id)}>删除</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}
        </div>
      )}

      {/* ================== Section C: Behavior Patterns ================== */}
      <div className="card">
        <div className="row" style={{ marginBottom: 8 }}>
          <h3 style={{ margin: 0 }}>③ 行为模式库（{patterns.length}）</h3>
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
            placeholder="搜索（name/typical_behavior）"
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
            {patterns.map((p) => <PatternCard key={p.id} pattern={p} onDelete={() => onDeletePattern(p.id)} />)}
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

function ChapterRow({
  chapter, busy, onRunStudy,
}: {
  chapter: StudyChapter; busy: boolean; onRunStudy: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="card" style={{ background: "var(--bg-elevated)" }}>
      <div className="row">
        <b>[{chapter.chapter_index}] {chapter.title || "未命名"}</b>
        <span className="muted tiny" style={{ marginLeft: 8 }}>
          {chapter.char_count} 字{chapter.last_studied_at ? ` · 已抽取 ${new Date(chapter.last_studied_at).toLocaleString()}` : ""}
        </span>
        <span className="spacer" />
        <button onClick={() => setExpanded(!expanded)}>{expanded ? "收起" : "查看正文"}</button>
        <button onClick={onRunStudy} disabled={busy}>
          {busy ? "抽取中…" : "抽取人物"}
        </button>
      </div>
      {expanded && (
        <pre className="failure-pre faint" style={{ marginTop: 8, maxHeight: 200 }}>
          {chapter.content}
        </pre>
      )}
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
