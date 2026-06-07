import { useEffect, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import {
  getBible, getProjectWorkspace, updateBible, listOutlines, createOutline, bulkCreateOutlines,
  listChapters, createChapter, getProject, getPolicy, updatePolicy,
  createTask, workerStart, listTasks, deleteProject, updateProject,
  exportProjectFile, type ProjectExportFormat,
} from "../api";
import type { Project, Bible, Outline, Chapter, WorkerPolicy, AgentTask, ProjectWorkspace } from "../types";
import { useProjectStore } from "../stores/projectStore";
import { ShelfBreadcrumb } from "../components/shelf";
import { LaunchProjectDialog } from "../components/projects/LaunchProjectDialog";

const TABS = [
  { key: "workspace", label: "书内" },
  { key: "overview", label: "概览" },
  { key: "bible", label: "主设定" },
  { key: "outlines", label: "大纲" },
  { key: "chapters", label: "章节" },
  { key: "policy", label: "策略" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export function ProjectPage() {
  const { pid } = useParams();
  const projectId = Number(pid);
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [tab, setTab] = useState<TabKey>("workspace");
  const [workspace, setWorkspace] = useState<ProjectWorkspace | null>(null);
  const [bible, setBible] = useState<Bible | null>(null);
  const [outlines, setOutlines] = useState<Outline[]>([]);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [policy, setPolicy] = useState<WorkerPolicy | null>(null);
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showLaunch, setShowLaunch] = useState(false);
  const selectProject = useProjectStore((s) => s.selectProject);

  const refreshWorkspace = async (params: { chapter_id?: number; chapter_no?: number } = {}) => {
    const data = await getProjectWorkspace(projectId, params);
    setWorkspace(data);
    setProject(data.project);
    setBible(data.bible);
    setTasks(data.latest_tasks as any);
  };

  useEffect(() => {
    selectProject(projectId);
    setErr(null);
    refreshWorkspace().catch((e) => setErr(e.message));
  }, [projectId, selectProject]);

  useEffect(() => {
    if (tab === "outlines" && outlines.length === 0) {
      listOutlines(projectId).then(setOutlines).catch(() => {});
    }
    if ((tab === "chapters" || tab === "overview") && chapters.length === 0) {
      listChapters(projectId).then(setChapters).catch(() => {});
    }
    if (tab === "bible" && bible === null) {
      getBible(projectId).then(setBible).catch(() => {});
    }
    if (tab === "policy" && policy === null) {
      getPolicy(projectId).then(setPolicy).catch(() => {});
    }
    if (tab === "overview" && tasks.length === 0) {
      listTasks({ project_id: projectId, limit: 10 }).then(setTasks).catch(() => {});
    }
  }, [tab, projectId, outlines.length, chapters.length, bible, policy, tasks.length]);

  const onStartPipeline = async (chapterId: number) => {
    setBusy(true);
    try {
      await createTask({
        project_id: projectId, chapter_id: chapterId,
        task_type: "chapter_pipeline", priority: 100, payload: { mode: "full" },
      });
      await workerStart();
      listTasks({ project_id: projectId, limit: 10 }).then(setTasks).catch(() => {});
    } catch (e: any) {
      alert(e.message ?? String(e));
    } finally { setBusy(false); }
  };

  const onDeleteProject = async () => {
    if (!project) return;
    if (!confirm(`确认删除项目「${project.name}」？所有数据将被清除。`)) return;
    try {
      await deleteProject(project.id);
      navigate("/projects");
    } catch (e: any) { alert(e.message ?? String(e)); }
  };

  const hasWorkspaceChapters = workspace?.toc.some((item) => item.chapter_id != null) ?? chapters.length > 0;

  if (err) return <div className="page-empty"><div className="big">无法加载</div>{err}</div>;
  if (!project) return <div className="page-empty"><span className="spinner" /> 加载项目…</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <ShelfBreadcrumb
        backTo="/projects"
        backLabel="返回项目书架"
        items={[
          { label: "项目书架", to: "/projects" },
          { label: project.name },
          { label: TABS.find((t) => t.key === tab)?.label ?? "" },
        ]}
      />
      <div className="subheader">
        <h2 className="serif">{project.name}</h2>
        <span className="badge gold">{project.genre}</span>
        <span className="meta">
          {project.chapter_count} / {project.target_chapter_count} 章 ·
          {" "}{project.total_words.toLocaleString()} / {project.target_word_count.toLocaleString()} 字
        </span>
        <div className="actions">
          {!hasWorkspaceChapters && (
            <button
              className="primary"
              onClick={() => setShowLaunch(true)}
              style={{
                background: "linear-gradient(135deg, var(--accent-gold, #3f7cff), var(--accent-violet, #7b61ff))",
                fontWeight: 600,
              }}
            >
              启动创作
            </button>
          )}
          <button onClick={onDeleteProject} className="danger">删除</button>
        </div>
      </div>

      {/* 启动创作弹窗 */}
      <LaunchProjectDialog
        open={showLaunch}
        projectId={projectId}
        projectName={project.name}
        onClose={() => setShowLaunch(false)}
        onLaunched={() => {
          refreshWorkspace().catch(() => {});
          listTasks({ project_id: projectId, limit: 10 }).then(setTasks).catch(() => {});
          listChapters(projectId).then(setChapters).catch(() => {});
          listOutlines(projectId).then(setOutlines).catch(() => {});
          workerStart().catch(() => {});
        }}
      />

      <div className="main-body" style={{ padding: 0, maxWidth: "100%" }}>
        <div className="tabs" style={{ padding: "0 24px" }}>
          {TABS.map((t) => (
            <button
              key={t.key}
              className={`tab ${tab === t.key ? "active" : ""}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div style={{ padding: "0 24px 24px" }}>
          {tab === "workspace" && (
            <BookWorkspaceTab
              workspace={workspace}
              onEditBible={() => setTab("bible")}
              onSelectChapter={(item) => {
                if (item.chapter_id) {
                  refreshWorkspace({ chapter_id: item.chapter_id }).catch((e) => setErr(e.message));
                } else {
                  refreshWorkspace({ chapter_no: item.chapter_no }).catch((e) => setErr(e.message));
                }
              }}
              onLaunch={() => setShowLaunch(true)}
            />
          )}
          {tab === "overview" && (
            <OverviewTab
              project={project}
              chapters={chapters}
              tasks={tasks}
              onLaunch={() => setShowLaunch(true)}
              onSaveMeta={async (patch) => {
                const updated = await updateProject(projectId, patch);
                setProject(updated);
              }}
            />
          )}
          {tab === "bible" && (
            <BibleTab bible={bible} onSave={async (b) => {
              const updated = await updateBible(projectId, b);
              setBible(updated);
            }} />
          )}
          {tab === "outlines" && (
            <OutlinesTab
              outlines={outlines}
              onAdd={async (o: Partial<Outline>) => {
                const created = await createOutline(projectId, o);
                setOutlines([...outlines, created].sort((a, b) => a.chapter_no - b.chapter_no));
              }}
              onBulk={async (items: Partial<Outline>[]) => {
                const created = await bulkCreateOutlines(projectId, items);
                setOutlines([...outlines, ...created].sort((a, b) => a.chapter_no - b.chapter_no));
              }}
            />
          )}
          {tab === "chapters" && (
            <ChaptersTab
              chapters={chapters}
              onAdd={async (c: Partial<Chapter>) => {
                const created = await createChapter(projectId, c);
                setChapters([...chapters, created].sort((a, b) => a.chapter_no - b.chapter_no));
              }}
              onStart={onStartPipeline}
              busy={busy}
            />
          )}
          {tab === "policy" && policy && (
            <PolicyTab policy={policy} onSave={async (p) => {
              const updated = await updatePolicy(projectId, p);
              setPolicy(updated);
            }} />
          )}
        </div>
      </div>
    </div>
  );
}

function BookWorkspaceTab({
  workspace,
  onEditBible,
  onSelectChapter,
  onLaunch,
}: {
  workspace: ProjectWorkspace | null;
  onEditBible: () => void;
  onSelectChapter: (item: ProjectWorkspace["toc"][number]) => void;
  onLaunch: () => void;
}) {
  if (!workspace) {
    return <div className="page-empty"><span className="spinner" /> 正在打开作品...</div>;
  }
  const selected = workspace.selected_chapter;
  const bibleContent = workspace.bible?.content ?? {};
  const worldItems = [
    ["世界观", bibleContent.world],
    ["主线", bibleContent.main_plot ?? bibleContent.plot],
    ["规则", bibleContent.rules ?? bibleContent.world_rules],
    ["主角", bibleContent.protagonist],
  ].filter(([, value]) => value !== undefined && value !== null && String(value).trim() !== "");
  const hasAnyChapter = workspace.toc.some((item) => item.chapter_id != null);

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "280px minmax(0, 1fr) 340px",
        gap: 16,
        alignItems: "start",
      }}
    >
      <aside className="card" style={{ position: "sticky", top: 12, maxHeight: "calc(100vh - 170px)", overflow: "auto" }}>
        <div className="card-header">
          <h3>目录</h3>
          <span className="muted small">{workspace.toc.length} 章</span>
        </div>
        {workspace.toc.length === 0 ? (
          <div>
            <div className="muted">这本书还没有目录。</div>
            <button className="primary" style={{ marginTop: 12, width: "100%" }} onClick={onLaunch}>
              启动创作
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {workspace.toc.map((item) => (
              <button
                key={`${item.chapter_no}-${item.chapter_id ?? "outline"}`}
                className={`ghost ${item.selected ? "active" : ""}`}
                onClick={() => onSelectChapter(item)}
                style={{
                  width: "100%",
                  textAlign: "left",
                  padding: "10px 12px",
                  border: item.selected ? "1px solid var(--accent-gold)" : "1px solid var(--border)",
                  background: item.selected ? "var(--surface-2)" : "transparent",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <strong>第 {item.chapter_no} 章</strong>
                  <span className={`pill ${item.has_content ? "succeeded" : "pending"}`}>
                    {item.has_content ? "有正文" : item.chapter_id ? "待生成" : "大纲"}
                  </span>
                </div>
                <div className="small" style={{ marginTop: 4 }}>{item.title}</div>
                <div className="muted tiny" style={{ marginTop: 4 }}>
                  {item.actual_word_count || 0} / {item.target_word_count || 0} 字
                </div>
              </button>
            ))}
          </div>
        )}
      </aside>

      <main className="card" style={{ minHeight: "calc(100vh - 170px)" }}>
        <div className="card-header">
          <div>
            <h3>{selected ? `第 ${selected.chapter_no} 章：${selected.title}` : workspace.project.name}</h3>
            {selected && (
              <div className="muted small">
                {selected.version_kind ? `${selected.version_kind} v${selected.version_no ?? "-"}` : "暂无正文版本"}
                {" · "}
                {selected.actual_word_count} / {selected.target_word_count} 字
                {selected.current_score != null ? ` · ${selected.current_score} 分` : ""}
              </div>
            )}
          </div>
          {selected?.id && <Link className="button" to={`/projects/${workspace.project.id}/chapters/${selected.id}`}>打开章节</Link>}
        </div>

        {!hasAnyChapter ? (
          <div className="page-empty" style={{ minHeight: 360 }}>
            <div className="big">这本书还没有章节</div>
            <div className="muted">可以先录入大纲，也可以让系统自动生成大纲、角色和世界观。</div>
            <button className="primary" style={{ marginTop: 16 }} onClick={onLaunch}>启动创作</button>
          </div>
        ) : selected?.content?.trim() ? (
          <article
            style={{
              whiteSpace: "pre-wrap",
              lineHeight: 1.9,
              fontSize: 16,
              maxWidth: 820,
              margin: "8px auto 0",
            }}
          >
            {selected.content}
          </article>
        ) : (
          <div className="page-empty" style={{ minHeight: 360 }}>
            <div className="big">这一章还没有正文</div>
            {selected?.outline_summary && <div className="muted" style={{ maxWidth: 680 }}>{selected.outline_summary}</div>}
            {selected?.id && (
              <Link className="button primary" style={{ marginTop: 16 }} to={`/projects/${workspace.project.id}/chapters/${selected.id}`}>
                去生成正文
              </Link>
            )}
          </div>
        )}
      </main>

      <aside style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <section className="card">
          <div className="card-header">
            <h3>世界观</h3>
            <button className="ghost" type="button" onClick={onEditBible}>编辑</button>
          </div>
          {worldItems.length === 0 ? (
            <div className="muted">还没有主设定。</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {worldItems.map(([label, value]) => (
                <div key={label}>
                  <div className="muted tiny">{label}</div>
                  <div className="small" style={{ whiteSpace: "pre-wrap" }}>{formatBibleValue(value)}</div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="card">
          <div className="card-header">
            <h3>角色</h3>
            <Link className="ghost" to={`/memory-shelf/${workspace.project.id}`}>{workspace.characters.length}</Link>
          </div>
          {workspace.characters.length === 0 ? (
            <div className="muted">还没有角色设定。</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {workspace.characters.slice(0, 8).map((character) => (
                <div key={character.id} style={{ borderBottom: "1px solid var(--border)", paddingBottom: 10 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <strong>{character.name}</strong>
                    <span className="pill">{roleLabel(character.role)}</span>
                  </div>
                  <div className="muted small" style={{ marginTop: 4 }}>
                    {character.latest_state?.current_goal || character.latest_state?.emotion_state || profileSummary(character.base_profile)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="card">
          <div className="card-header">
            <h3>最近任务</h3>
            <Link className="ghost" to="/tasks">全部</Link>
          </div>
          {workspace.latest_tasks.length === 0 ? (
            <div className="muted">暂无任务。</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {workspace.latest_tasks.slice(0, 5).map((task) => (
                <div key={task.id} className="small" style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <span>{task.display_title || task.task_kind || task.task_type}</span>
                  <span className={`pill ${task.status}`}>{task.status}</span>
                </div>
              ))}
            </div>
          )}
        </section>
      </aside>
    </div>
  );
}

function formatBibleValue(value: any): string {
  if (Array.isArray(value)) return value.join("\n");
  if (typeof value === "object" && value !== null) return JSON.stringify(value, null, 2);
  return String(value ?? "");
}

function profileSummary(profile: Record<string, any>): string {
  return profile.description || profile.summary || profile.goal || "暂无动态";
}

function roleLabel(role: string): string {
  const map: Record<string, string> = {
    protagonist: "主角",
    antagonist: "反派",
    villain: "反派",
    heroine: "女主",
    support: "配角",
    supporting: "配角",
  };
  return map[role] ?? role;
}

function OverviewTab({ project, chapters, tasks, onLaunch, onSaveMeta }: {
  project: Project;
  chapters: Chapter[];
  tasks: AgentTask[];
  onLaunch: () => void;
  onSaveMeta: (patch: Partial<Project>) => Promise<void>;
}) {
  const [exportFormat, setExportFormat] = useState<ProjectExportFormat>("markdown");
  const [exportBusy, setExportBusy] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const done = chapters.filter((c) => c.status === "done").length;
  const reviewing = chapters.filter((c) => c.status === "needs_review").length;
  const totalWords = chapters.reduce((s, c) => s + c.actual_word_count, 0);
  const avgScore = chapters.filter((c) => c.current_score != null).reduce((s, c) => s + (c.current_score ?? 0), 0)
    / Math.max(1, chapters.filter((c) => c.current_score != null).length);
  const progressPct = Math.min(100, (totalWords / project.target_word_count) * 100);
  const onExport = async () => {
    setExportBusy(true);
    setExportError(null);
    try {
      const { blob, filename } = await exportProjectFile(project.id, exportFormat);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e: any) {
      setExportError(e?.message ?? String(e));
    } finally {
      setExportBusy(false);
    }
  };

  return (
    <div>
      {/* 启动创作提示 (章节为0时显示) */}
      {chapters.length === 0 && (
        <div className="card" style={{
          background: "linear-gradient(135deg, rgba(63,124,255,0.08), rgba(123,97,255,0.05))",
          border: "1px dashed var(--accent-gold, #3f7cff)",
          textAlign: "center",
          padding: "32px 24px",
        }}>
          <div style={{ fontSize: 36, marginBottom: 8 }}>📝</div>
          <h3 style={{ margin: "0 0 8px" }}>项目已就绪，开始创作吧！</h3>
          <p style={{ color: "var(--text-secondary)", margin: "0 0 16px", fontSize: 14 }}>
            选择半自动模式提供大纲和人物，或全自动模式让 AI 生成一切
          </p>
          <button
            className="primary"
            onClick={onLaunch}
            style={{
              background: "linear-gradient(135deg, var(--accent-gold, #3f7cff), var(--accent-violet, #7b61ff))",
              padding: "10px 28px",
              fontSize: 15,
              fontWeight: 600,
            }}
          >
            启动创作
          </button>
        </div>
      )}
      <div className="stat-grid">
        <div className="stat"><div className="label">已完成章节</div><div className="num">{done}</div><div className="sub">共 {chapters.length} 章</div></div>
        <div className="stat"><div className="label">待复盘</div><div className="num">{reviewing}</div><div className="sub">分数低于 80</div></div>
        <div className="stat"><div className="label">已写字数</div><div className="num">{(totalWords / 10000).toFixed(1)}万</div><div className="sub">目标 {project.target_word_count.toLocaleString()}</div></div>
        <div className="stat"><div className="label">平均分</div><div className="num">{isNaN(avgScore) ? "—" : avgScore.toFixed(1)}</div><div className="sub">仅统计已评分章节</div></div>
      </div>

      <div className="card">
        <h3>总进度</h3>
        <div className="progress"><div className="fill" style={{ width: `${progressPct}%` }} /></div>
        <div className="muted tiny" style={{ marginTop: 6 }}>{progressPct.toFixed(1)}% · 目标 {project.target_word_count.toLocaleString()} 字 / {project.target_chapter_count} 章</div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3>导出成品</h3>
          <span className="muted small">{chapters.length} 章 · 优先导出 final 版本</span>
        </div>
        <div className="row gap-3" style={{ alignItems: "end" }}>
          <div style={{ width: 220 }}>
            <label>导出格式</label>
            <select
              value={exportFormat}
              onChange={(e) => setExportFormat(e.target.value as ProjectExportFormat)}
            >
              <option value="markdown">Markdown (.md)</option>
              <option value="txt">纯文本 (.txt)</option>
              <option value="html">网页 (.html)</option>
              <option value="json">结构化 JSON</option>
            </select>
          </div>
          <div className="muted small" style={{ flex: 1 }}>
            系统会按 final → rewrite → draft 的顺序收集每章正文；没有正文的章节会明确标记，导出结果会直接下载。
          </div>
          <button className="primary" onClick={onExport} disabled={exportBusy || chapters.length === 0}>
            {exportBusy ? "导出中..." : "导出成品"}
          </button>
        </div>
        {exportError && <div className="error" style={{ marginTop: 10 }}>{exportError}</div>}
      </div>

      {/* Round 2: sidebar grouping metadata — edit the bucket this
          project belongs to, or pin it to the top of the ProjectNav. */}
      <div className="card">
        <h3>侧边栏分组</h3>
        <p className="muted small" style={{ marginTop: -6, marginBottom: 10 }}>
          「分类」决定左侧项目栏的项目归到哪个分组；「置顶」会把它浮在所有分组之上。
        </p>
        <div className="row gap-3" style={{ alignItems: "center" }}>
          <div style={{ flex: 1 }}>
            <label>分类</label>
            <input
              defaultValue={project.category ?? ""}
              placeholder={`留空则使用类型「${project.genre}」`}
              onBlur={(e) => {
                const next = e.target.value.trim() || null;
                if (next !== (project.category ?? null)) {
                  onSaveMeta({ category: next }).catch((err: any) => alert(err.message));
                }
              }}
            />
          </div>
          <div>
            <label className="row" style={{ marginBottom: 0, whiteSpace: "nowrap" }}>
              <input
                type="checkbox"
                defaultChecked={project.pinned}
                style={{ width: "auto" }}
                onChange={(e) => onSaveMeta({ pinned: e.target.checked }).catch((err: any) => alert(err.message))}
              />
              <span style={{ marginLeft: 6 }}>📌 置顶</span>
            </label>
          </div>
        </div>
      </div>

      <div className="card">
        <h3>最近任务</h3>
        {tasks.length === 0 ? (
          <div className="muted">还没有任务。在「章节」标签页选一章开始流水线。</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>#</th><th>章节</th><th>状态</th>
                <th style={{ textAlign: "right" }}>成本</th>
                <th style={{ textAlign: "right" }}>Tokens</th>
                <th>时间</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((t) => (
                <tr key={t.id}>
                  <td className="mono muted">{t.id}</td>
                  <td>{t.chapter_id ? <Link to={`/projects/${t.project_id}/chapters/${t.chapter_id}`}>第 {t.chapter_id} 章</Link> : "—"}</td>
                  <td><span className={`pill ${t.status}`}>{t.status}</span></td>
                  <td className="mono" style={{ textAlign: "right" }}>${t.cost_usd.toFixed(4)}</td>
                  <td className="mono muted" style={{ textAlign: "right" }}>{(t.input_tokens / 1000).toFixed(1)}k / {(t.output_tokens / 1000).toFixed(1)}k</td>
                  <td className="muted tiny">{formatTime(t.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function BibleTab({ bible, onSave }: { bible: Bible | null; onSave: (b: any) => Promise<void> }) {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (bible) {
      setTitle(bible.title);
      setContent(JSON.stringify(bible.content, null, 2));
    }
  }, [bible]);
  if (!bible) return <div className="muted">没有主设定记录。</div>;
  return (
    <div className="card">
      <h3>主设定</h3>
      <label>标题</label>
      <input value={title} onChange={(e) => setTitle(e.target.value)} />
      <label style={{ marginTop: 12 }}>内容（JSON 格式）</label>
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        style={{ minHeight: 320, fontFamily: "var(--font-mono)" }}
      />
      <div className="row" style={{ marginTop: 12 }}>
        <span className="muted small">版本 v{bible.version} · 更新于 {bible.updated_at}</span>
        <span className="spacer" />
        <button onClick={async () => {
          setBusy(true);
          try {
            const parsed = JSON.parse(content);
            await onSave({ title, content: parsed });
          } catch (e: any) { alert("JSON 解析失败：" + e.message); }
          finally { setBusy(false); }
        }} disabled={busy} className="primary">{busy ? "保存中…" : "保存设定"}</button>
      </div>
    </div>
  );
}

function OutlinesTab({ outlines, onAdd, onBulk }: any) {
  const [bulk, setBulk] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div>
      <div className="card">
        <h3>批量添加大纲（每行一个）</h3>
        <p className="muted small">格式：<code>章节号|标题|简介|重要性(0-100)</code></p>
        <textarea
          value={bulk}
          onChange={(e) => setBulk(e.target.value)}
          rows={5}
          placeholder={`1|开局被逐|主角因废脉被宗门除名|80\n2|残玉觉醒|主角跌入山谷偶得残玉|85`}
        />
        <div className="row" style={{ marginTop: 8 }}>
          <span className="spacer" />
          <button className="primary" disabled={!bulk.trim() || busy} onClick={async () => {
            setBusy(true);
            try {
              const items = bulk.split("\n").map((l) => l.trim()).filter(Boolean).map((line) => {
                const [no, title, summary, importance] = line.split("|").map((s) => s.trim());
                return {
                  volume_no: 1, chapter_no: Number(no), title, summary,
                  importance: importance ? Number(importance) : 50,
                };
              });
              await onBulk(items);
              setBulk("");
            } catch (e: any) { alert(e.message); }
            finally { setBusy(false); }
          }}>批量添加</button>
        </div>
      </div>

      <div className="card">
        <h3>大纲列表 ({outlines.length})</h3>
        {outlines.length === 0 ? (
          <div className="muted">还没有大纲条目。</div>
        ) : (
          <table>
            <thead>
              <tr><th>章节</th><th>标题</th><th>简介</th><th style={{ textAlign: "right" }}>重要性</th><th>状态</th></tr>
            </thead>
            <tbody>
              {outlines.map((o: Outline) => (
                <tr key={o.id}>
                  <td className="mono">第 {o.chapter_no} 章</td>
                  <td>{o.title}</td>
                  <td className="muted small ellipsis" style={{ maxWidth: 400 }}>{o.summary ?? "—"}</td>
                  <td className="mono" style={{ textAlign: "right" }}>{o.importance}</td>
                  <td><span className="pill">{o.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function ChaptersTab({ chapters, onAdd, onStart, busy }: any) {
  const [no, setNo] = useState(1);
  const [title, setTitle] = useState("");
  return (
    <div>
      <div className="card">
        <h3>新建章节</h3>
        <div className="row gap-3">
          <div style={{ width: 120 }}>
            <label>章节号</label>
            <input type="number" value={no} min={1} onChange={(e) => setNo(Number(e.target.value))} />
          </div>
          <div style={{ flex: 1 }}>
            <label>标题</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="例：第一章 落魄" />
          </div>
          <div className="spacer" />
          <button className="primary" disabled={!title.trim()} onClick={async () => {
            await onAdd({ chapter_no: no, title, target_word_count: 3000 });
            setTitle("");
            setNo(no + 1);
          }}>+ 添加</button>
        </div>
      </div>

      <div className="card">
        <h3>章节列表 ({chapters.length})</h3>
        {chapters.length === 0 ? (
          <div className="muted">还没有章节。先在上方添加章节，然后点「开始流水线」让 Worker 处理。</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>章节</th><th>标题</th><th>状态</th>
                <th style={{ textAlign: "right" }}>目标 / 实际</th>
                <th style={{ textAlign: "right" }}>分数</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {chapters.map((c: Chapter) => (
                <tr key={c.id}>
                  <td className="mono">第 {c.chapter_no} 章</td>
                  <td><Link to={`/projects/${c.project_id}/chapters/${c.id}`}>{c.title}</Link></td>
                  <td><span className={`pill ${c.status}`}>{c.status}</span></td>
                  <td className="mono" style={{ textAlign: "right" }}>{c.target_word_count} / {c.actual_word_count}</td>
                  <td className="mono" style={{ textAlign: "right" }}>
                    {c.current_score != null ? <span className={`score-pill ${scoreClass(c.current_score)}`}>{c.current_score}</span> : "—"}
                  </td>
                  <td>
                    <button
                      disabled={busy || c.status === "drafting"}
                      onClick={() => onStart(c.id)}
                    >
                      {c.status === "drafting" ? "处理中…" : "开始流水线"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function PolicyTab({ policy, onSave }: { policy: WorkerPolicy; onSave: (p: any) => Promise<void> }) {
  const [form, setForm] = useState(policy);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setForm(policy); }, [policy]);
  return (
    <div className="card">
      <h3>Worker 策略</h3>
      <div className="grid-2">
        <div>
          <label>每日字数目标</label>
          <input type="number" value={form.daily_word_goal} onChange={(e) => setForm({ ...form, daily_word_goal: Number(e.target.value) })} />
        </div>
        <div>
          <label>每日预算 (USD)</label>
          <input type="number" step="0.1" value={form.daily_budget_usd} onChange={(e) => setForm({ ...form, daily_budget_usd: Number(e.target.value) })} />
        </div>
        <div>
          <label>通过分数 (0-100)</label>
          <input type="number" min={0} max={100} value={form.pass_score} onChange={(e) => setForm({ ...form, pass_score: Number(e.target.value) })} />
        </div>
        <div>
          <label>最大改稿轮次</label>
          <input type="number" min={0} max={5} value={form.max_rewrite_rounds} onChange={(e) => setForm({ ...form, max_rewrite_rounds: Number(e.target.value) })} />
        </div>
        <div>
          <label>任务最大重试</label>
          <input type="number" min={0} max={10} value={form.max_retry_per_task} onChange={(e) => setForm({ ...form, max_retry_per_task: Number(e.target.value) })} />
        </div>
        <div>
          <label>连续失败停机阈值</label>
          <input type="number" min={1} max={10} value={form.consecutive_fail_stop} onChange={(e) => setForm({ ...form, consecutive_fail_stop: Number(e.target.value) })} />
        </div>
      </div>
      <div className="row" style={{ marginTop: 12 }}>
        <label className="row" style={{ marginBottom: 0 }}>
          <input type="checkbox" checked={form.auto_continue} onChange={(e) => setForm({ ...form, auto_continue: e.target.checked })} style={{ width: "auto" }} />
          <span style={{ marginLeft: 6 }}>完成后自动续写下一章</span>
        </label>
        <span className="spacer" />
        <button className="primary" disabled={busy} onClick={async () => {
          setBusy(true);
          try { await onSave(form); }
          finally { setBusy(false); }
        }}>保存策略</button>
      </div>
    </div>
  );
}

function scoreClass(s: number) {
  if (s >= 80) return "pass";
  if (s >= 60) return "fail";
  return "low";
}

function formatTime(iso: string) {
  try { return new Date(iso).toLocaleString("zh-CN", { hour: "2-digit", minute: "2-digit" }); }
  catch { return iso; }
}
