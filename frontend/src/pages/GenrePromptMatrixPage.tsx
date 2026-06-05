/**
 * GenrePromptMatrixPage — Agent × Genre prompt mapping matrix with drag-drop.
 * P7: drag templates from pool to cells, double-click to pick, right-click to unbind.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  DndContext, DragEndEvent, DragOverlay, DragStartEvent,
  PointerSensor, useSensor, useSensors, closestCenter,
} from "@dnd-kit/core";
import {
  getGenrePromptMatrix, bindGenrePrompt, unbindGenrePrompt,
  getAvailableTemplates, getProjectPromptAudit,
  createPromptTemplate, listPromptTemplates, listProjects,
} from "../api";
import type {
  GenrePromptMatrixResponse, MatrixCell, PromptSnapshotDetail,
  PromptTemplate, Project,
} from "../types";
import "./GenrePromptMatrixPage.css";

// NF2 fix: 不再硬编码 Agent 行和 Genre 列，从后端 matrix API 获取
// 如果后端返回为空则使用默认值
const FALLBACK_GENRE_LIST = ["玄幻", "都市", "科幻", "历史", "悬疑", "言情"];
const FALLBACK_AGENT_ROWS = [
  "planner", "drafter", "critic", "rewriter", "continuity", "memory_update",
  "reader_hook", "reader_emotion", "reader_logic", "reader_commercial", "reader_toxic",
  "chief_comment_moderator", "discussion", "learner", "study",
];
const AGENT_LABELS: Record<string, string> = {
  planner: "Planner", drafter: "Drafter", critic: "Critic",
  rewriter: "Rewriter", continuity: "Continuity", memory_update: "Memory",
  reader_hook: "Reader·钩子", reader_emotion: "Reader·情绪",
  reader_logic: "Reader·逻辑", reader_commercial: "Reader·商业",
  reader_toxic: "Reader·毒点", chief_comment_moderator: "Chief·评论接入官",
  discussion: "Discussion", learner: "Learner", study: "Study",
};
// Agent 分组 (NF2 §9.3)
const AGENT_SECTIONS = [
  { key: "writing", label: "写作 Agent", agents: ["planner", "drafter", "critic", "rewriter", "continuity"] },
  { key: "reader", label: "读者评审 Agent", agents: ["reader_hook", "reader_emotion", "reader_logic", "reader_commercial", "reader_toxic"] },
  { key: "chief", label: "主 Agent / 讨论", agents: ["chief_comment_moderator", "discussion"] },
  { key: "memory", label: "记忆 Agent", agents: ["memory_update"] },
  { key: "study", label: "拆书 Agent", agents: ["learner", "study"] },
];

export function GenrePromptMatrixPage() {
  const [matrix, setMatrix] = useState<GenrePromptMatrixResponse | null>(null);
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [filter, setFilter] = useState("全部");
  const [loading, setLoading] = useState(true);
  const [activeDrag, setActiveDrag] = useState<PromptTemplate | null>(null);
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; cell: MatrixCell } | null>(null);
  const [picker, setPicker] = useState<{ agentKey: string; genre: string; x: number; y: number } | null>(null);
  const [availTemplates, setAvailTemplates] = useState<{ id: number; template_key: string; name: string }[]>([]);
  // Traceability
  const [projects, setProjects] = useState<Project[]>([]);
  const [auditProject, setAuditProject] = useState<number | null>(null);
  const [snapshots, setSnapshots] = useState<PromptSnapshotDetail[]>([]);
  // New template
  const [showNew, setShowNew] = useState(false);
  const [newTpl, setNewTpl] = useState({ template_key: "", name: "", category: "writing", role: "Draft", genre: "", initial_body: "" });

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));
  const containerRef = useRef<HTMLDivElement>(null);

  const reload = useCallback(async () => {
    try {
      const [m, t] = await Promise.all([getGenrePromptMatrix(), listPromptTemplates()]);
      setMatrix(m);
      setTemplates(t);
    } catch { /* */ }
    setLoading(false);
  }, []);

  useEffect(() => { reload(); }, [reload]);
  useEffect(() => { listProjects().then(setProjects).catch(() => {}); }, []);
  useEffect(() => {
    if (auditProject) getProjectPromptAudit(auditProject).then(setSnapshots).catch(() => setSnapshots([]));
    else setSnapshots([]);
  }, [auditProject]);

  // Close context menu on click elsewhere
  useEffect(() => {
    const close = () => { setCtxMenu(null); setPicker(null); };
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, []);

  const getCell = (agentKey: string, genre: string): MatrixCell | undefined =>
    matrix?.cells.find((c) => c.agent_role_key === agentKey && c.genre === genre);

  const genreList = matrix?.genres?.length ? matrix.genres : FALLBACK_GENRE_LIST;
  const agentRows = matrix?.agent_role_keys?.length ? matrix.agent_role_keys : FALLBACK_AGENT_ROWS;
  const genresToShow = filter === "全部" ? genreList : [filter];

  const onDragStart = (e: DragStartEvent) => {
    const tpl = templates.find((t) => t.id === Number(e.active.id));
    setActiveDrag(tpl || null);
  };

  const onDragEnd = async (e: DragEndEvent) => {
    setActiveDrag(null);
    const { active, over } = e;
    if (!over) return;
    const tplId = Number(active.id);
    const overId = String(over.id); // "agentKey:genre"
    const [agentKey, genre] = overId.split(":");
    if (!agentKey || !genre) return;
    try {
      await bindGenrePrompt({ agent_role_key: agentKey, genre, prompt_template_id: tplId });
      await reload();
    } catch (err: any) { alert(err.message || "绑定失败"); }
  };

  const handleDoubleClick = async (agentKey: string, genre: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const list = await getAvailableTemplates(agentKey, genre);
      setAvailTemplates(list);
      setPicker({ agentKey, genre, x: e.clientX, y: e.clientY });
    } catch { /* */ }
  };

  const handlePick = async (tplId: number) => {
    if (!picker) return;
    try {
      await bindGenrePrompt({ agent_role_key: picker.agentKey, genre: picker.genre, prompt_template_id: tplId });
      setPicker(null);
      await reload();
    } catch (err: any) { alert(err.message || "绑定失败"); }
  };

  const handleUnbind = async (cell: MatrixCell) => {
    if (!cell.prompt_template_id) return;
    try {
      await unbindGenrePrompt({ agent_role_key: cell.agent_role_key, genre: cell.genre, prompt_template_id: cell.prompt_template_id });
      setCtxMenu(null);
      await reload();
    } catch (err: any) { alert(err.message || "解绑失败"); }
  };

  const handleCreate = async () => {
    if (!newTpl.template_key || !newTpl.name) { alert("Key 和名称必填"); return; }
    try {
      await createPromptTemplate({
        template_key: newTpl.template_key, name: newTpl.name,
        category: newTpl.category, role: newTpl.role,
        genre: newTpl.genre || null, initial_body: newTpl.initial_body,
      });
      setShowNew(false);
      setNewTpl({ template_key: "", name: "", category: "writing", role: "Draft", genre: "", initial_body: "" });
      await reload();
    } catch (err: any) { alert(err.message || "创建失败"); }
  };

  if (loading) return <div className="page-empty"><div className="big">加载中…</div></div>;

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragStart={onDragStart} onDragEnd={onDragEnd}>
      <div className="gpm-page" ref={containerRef}>
        <div className="page-header" style={{ padding: "18px 24px 0" }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>Prompt 类型矩阵</h2>
          <p className="muted" style={{ margin: "4px 0 0", fontSize: 12 }}>拖拽模板到单元格绑定，双击空白格选择模板，右键解绑</p>
        </div>

        {/* Genre filter tabs — 使用后端返回的 genre 列表 */}
        <div className="gpm-genre-tabs">
          {["全部", ...genreList].map((g) => (
            <button key={g} className={`gpm-genre-tab ${filter === g ? "active" : ""}`}
              onClick={() => setFilter(g)}>{g}</button>
          ))}
        </div>

        <div className="gpm-content">
          {/* Matrix — 按 Section 分组渲染 (NF2 §9.3) */}
          <div className="gpm-matrix-wrap">
            {AGENT_SECTIONS.map((section) => {
              const sectionAgents = agentRows.filter((ak: string) => section.agents.includes(ak));
              if (sectionAgents.length === 0) return null;
              return (
                <div key={section.key} style={{ marginBottom: 16 }}>
                  <div className="muted small" style={{ padding: "6px 8px", fontWeight: 600, borderBottom: "1px solid var(--line)" }}>
                    {section.label}
                  </div>
                  <table className="gpm-matrix">
                    <thead>
                      <tr>
                        <th>角色 \ 类型</th>
                        {genresToShow.map((g: string) => <th key={g}>{g}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {sectionAgents.map((ak: string) => (
                        <tr key={ak}>
                          <th>{AGENT_LABELS[ak] || ak}</th>
                          {genresToShow.map((g: string) => {
                            const cell = getCell(ak, g);
                            const state = cell?.state || "empty";
                            return (
                              <td key={`${ak}:${g}`}>
                                <div
                                  id={`${ak}:${g}`}
                                  className={`gpm-cell ${state}`}
                                  onDoubleClick={(e) => handleDoubleClick(ak, g, e)}
                                  onContextMenu={(e) => {
                                    e.preventDefault();
                                    if (cell?.prompt_template_id) setCtxMenu({ x: e.clientX, y: e.clientY, cell });
                                  }}
                                >
                                  {cell?.template_name ? (
                                    <span className="gpm-cell-name">{cell.template_name}</span>
                                  ) : state === "fallback" ? (
                                    <span className="gpm-cell-placeholder">继承通用</span>
                                  ) : (
                                    <span className="gpm-cell-placeholder">---</span>
                                  )}
                                </div>
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            })}
          </div>

          {/* Template pool */}
          <div className="gpm-pool">
            <div className="gpm-pool-header">
              <h3>📦 模板池</h3>
              <span className="spacer" />
              <button className="btn btn-sm" onClick={() => setShowNew(true)}>+ 新建模板</button>
            </div>
            <div className="gpm-pool-grid">
              {templates.map((t) => (
                <div key={t.id} className="gpm-pool-chip" data-draggable-id={String(t.id)}>
                  {t.name}
                  <span className="gpm-chip-key">{t.genre || "通用"}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Traceability */}
          <div className="gpm-trace">
            <div className="gpm-trace-header">
              <h3>📋 追溯</h3>
              <select value={auditProject ?? ""} onChange={(e) => setAuditProject(e.target.value ? Number(e.target.value) : null)}>
                <option value="">选择项目…</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
            {snapshots.length === 0 ? (
              <div className="gpm-trace-empty">选择项目查看各章节使用的提示词快照</div>
            ) : (
              <div className="gpm-trace-list">
                {snapshots.map((s) => (
                  <div key={s.id} className="gpm-trace-row">
                    <span className="chapter">{s.chapter_title || `#${s.chapter_id}`}</span>
                    <span className="trigger">{s.trigger}</span>
                    <span className="snapshots">
                      {Object.entries(s.snapshot_data).map(([k, v]) => `${k}:${v.template_key}`).join(" · ")}
                    </span>
                    <span className="date">{new Date(s.created_at).toLocaleDateString()}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Context menu */}
        {ctxMenu && (
          <div className="gpm-ctx-menu" style={{ left: ctxMenu.x, top: ctxMenu.y }}>
            <button className="gpm-ctx-item danger" onClick={() => handleUnbind(ctxMenu.cell)}>解绑</button>
          </div>
        )}

        {/* Template picker */}
        {picker && (
          <div className="gpm-picker-dropdown" style={{ left: picker.x, top: picker.y }} onClick={(e) => e.stopPropagation()}>
            {availTemplates.length === 0 ? (
              <div className="gpm-picker-empty">无可用模板</div>
            ) : availTemplates.map((t) => (
              <button key={t.id} className="gpm-picker-item" onClick={() => handlePick(t.id)}>
                {t.name}
                <span className="gpm-picker-item-key">{t.template_key}</span>
              </button>
            ))}
          </div>
        )}

        {/* New template form */}
        {showNew && (
          <div style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center" }}
            onClick={() => setShowNew(false)}>
            <div className="gpm-new-form" style={{ width: 500, padding: 24 }} onClick={(e) => e.stopPropagation()}>
              <h3>新建 Prompt 模板</h3>
              <div className="gpm-new-form-grid">
                <div><label>名称</label><input value={newTpl.name} onChange={(e) => setNewTpl({ ...newTpl, name: e.target.value, template_key: e.target.value.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "") })} /></div>
                <div><label>Key</label><input value={newTpl.template_key} onChange={(e) => setNewTpl({ ...newTpl, template_key: e.target.value })} /></div>
                <div><label>分类</label>
                  <select value={newTpl.category} onChange={(e) => setNewTpl({ ...newTpl, category: e.target.value })}>
                    <option value="writing">writing</option><option value="review">review</option>
                    <option value="study">study</option><option value="memory">memory</option>
                  </select>
                </div>
                <div><label>角色</label>
                  <select value={newTpl.role} onChange={(e) => setNewTpl({ ...newTpl, role: e.target.value })}>
                    <option value="Draft">Draft</option><option value="Planner">Planner</option>
                    <option value="Critic">Critic</option><option value="Rewrite">Rewrite</option>
                  </select>
                </div>
                <div><label>类型</label>
                  <select value={newTpl.genre} onChange={(e) => setNewTpl({ ...newTpl, genre: e.target.value })}>
                    <option value="">通用</option>{genreList.map((g: string) => <option key={g} value={g}>{g}</option>)}
                  </select>
                </div>
              </div>
              <label>初始正文</label>
              <textarea value={newTpl.initial_body} onChange={(e) => setNewTpl({ ...newTpl, initial_body: e.target.value })} rows={8} style={{ fontFamily: "var(--font-mono)" }} />
              <div className="gpm-new-form-actions">
                <button onClick={() => setShowNew(false)}>取消</button>
                <button className="primary" onClick={handleCreate}>创建</button>
              </div>
            </div>
          </div>
        )}
      </div>

      <DragOverlay>
        {activeDrag ? (
          <div className="gpm-drag-overlay">{activeDrag.name}</div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}
