import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useProjectStore } from "../stores/projectStore";
import { createProject, deleteProject } from "../api";
import type { Project } from "../types";
import "./ProjectsPage.css";

const GENRES = ["玄幻", "都市", "历史", "科幻", "悬疑", "言情", "武侠", "仙侠", "奇幻", "军事", "游戏", "体育"];

export function ProjectsPage() {
  const projects = useProjectStore((s) => s.projects);
  const refresh = useProjectStore((s) => s.refresh);
  const remove = useProjectStore((s) => s.removeProject);
  const select = useProjectStore((s) => s.selectProject);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [genre, setGenre] = useState("玄幻");
  const [targetWords, setTargetWords] = useState(3_000_000);
  const [targetChapters, setTargetChapters] = useState(2000);
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  useEffect(() => { refresh(); }, [refresh]);

  const onCreate = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const p = await createProject({
        name: name.trim(), genre,
        target_word_count: targetWords, target_chapter_count: targetChapters,
        description: description.trim() || null,
      });
      setCreating(false);
      setName(""); setDescription("");
      await refresh();
      select(p.id);
      navigate(`/projects/${p.id}`);
    } catch (e: any) {
      alert(e.message ?? String(e));
    } finally { setBusy(false); }
  };

  const onDelete = async (p: Project) => {
    if (!confirm(`确认删除「${p.name}」？所有章节、记忆、任务都会被清除。`)) return;
    try {
      await deleteProject(p.id);
      remove(p.id);
    } catch (e: any) { alert(e.message ?? String(e)); }
  };

  return (
    <div className="projects-page">
      <header className="page-header">
        <div>
          <h1 className="page-title">项目</h1>
          <p className="page-subtitle">一本书 = 一个项目。每个项目独立维护设定、大纲、章节与记忆。</p>
        </div>
        <button className="primary" onClick={() => setCreating(true)}>+ 新建项目</button>
      </header>

      <div className="projects-grid">
        {projects.length === 0 ? (
          <div className="empty-large">
            <div className="empty-large-glyph">书</div>
            <h3>还没有项目</h3>
            <p>点右上角「+ 新建项目」开始你的第一本书。</p>
          </div>
        ) : projects.map((p) => (
          <div key={p.id} className="project-card" onClick={() => { select(p.id); navigate(`/projects/${p.id}`); }}>
            <div className="project-card-header">
              <span className="badge gold">{p.genre}</span>
              <span className="badge green">{p.status === "active" ? "进行中" : p.status}</span>
              <span className="spacer" />
              <button className="ghost tiny" onClick={(e) => { e.stopPropagation(); onDelete(p); }}>删除</button>
            </div>
            <h3 className="project-card-title">{p.name}</h3>
            {p.description && <p className="project-card-desc">{p.description}</p>}
            <div className="project-card-stats">
              <div>
                <div className="kpi-value serif" style={{ fontSize: 18 }}>{p.chapter_count}</div>
                <div className="kpi-sub">已写章节</div>
              </div>
              <div>
                <div className="kpi-value serif" style={{ fontSize: 18 }}>{formatNumber(p.total_words)}</div>
                <div className="kpi-sub">已写字数</div>
              </div>
              <div>
                <div className="kpi-value serif" style={{ fontSize: 18 }}>{Math.round((p.total_words / p.target_word_count) * 100)}%</div>
                <div className="kpi-sub">字数进度</div>
              </div>
            </div>
            <div className="project-card-bar">
              <div className="project-card-bar-fill" style={{ width: `${Math.min(100, (p.total_words / p.target_word_count) * 100)}%` }} />
            </div>
            <div className="project-card-target muted small">
              目标：{formatNumber(p.target_word_count)}字 / {p.target_chapter_count}章
            </div>
          </div>
        ))}
      </div>

      {creating && (
        <div className="modal-backdrop" onClick={() => setCreating(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>新建项目</h3>
            <label>书名</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="例：落魄剑仙录" autoFocus />
            <div className="row" style={{ gap: 12 }}>
              <div style={{ flex: 1 }}>
                <label>类型</label>
                <select value={genre} onChange={(e) => setGenre(e.target.value)}>
                  {GENRES.map((g) => <option key={g} value={g}>{g}</option>)}
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <label>目标字数</label>
                <input type="number" value={targetWords} min={10000} step={100000}
                  onChange={(e) => setTargetWords(parseInt(e.target.value || "0"))} />
              </div>
              <div style={{ flex: 1 }}>
                <label>目标章节</label>
                <input type="number" value={targetChapters} min={10}
                  onChange={(e) => setTargetChapters(parseInt(e.target.value || "0"))} />
              </div>
            </div>
            <label>简介（可选）</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3}
              placeholder="一句话说明这本书的核心看点" />
            <div className="row" style={{ marginTop: 12 }}>
              <span className="muted small">创建后会自动生成主设定、默认 Worker 策略</span>
              <span className="spacer" />
              <button onClick={() => setCreating(false)}>取消</button>
              <button className="primary" onClick={onCreate} disabled={!name.trim() || busy}>
                {busy ? "创建中…" : "创建"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function formatNumber(n: number): string {
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`;
  return n.toLocaleString();
}
