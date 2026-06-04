import { useEffect, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import {
  getChapter, listChapterVersions, listChapterSteps, getLatestVersion, taskEvents, taskSteps,
  createTask, workerStart,
} from "../api";
import type { Chapter, ChapterVersion, AgentStep } from "../types";
import { useProjectStore } from "../stores/projectStore";
import { ChapterCompare } from "../components/chapter/ChapterCompare";
import { ShelfBreadcrumb } from "../components/shelf";
import "../components/chapter/ChapterCompare.css";

const TABS = [
  { key: "manuscript", label: "正文" },
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
  const [tab, setTab] = useState<"manuscript" | "compare" | "versions" | "timeline" | "context">("manuscript");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    selectProject(projectId);
    const load = () => {
      getChapter(chapterId).then(setChapter).catch(() => navigate(`/projects/${projectId}`));
      listChapterVersions(chapterId).then(setVersions).catch(() => {});
      listChapterSteps(chapterId).then((data: any[]) => {
        // backend may return raw dicts; coerce into AgentStep-like
        setSteps(data as AgentStep[]);
      }).catch(() => {});
      getLatestVersion(chapterId, "final").then(setActiveVersion).catch(() => {
        // fall back to most recent draft
        getLatestVersion(chapterId, "draft").then(setActiveVersion).catch(() => {});
      });
    };
    load();
    const t = window.setInterval(load, 3000);
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

  if (!chapter) return <div className="page-empty"><span className="spinner" /> 加载章节…</div>;

  const contentText = activeVersion?.content ?? "(本章还没有任何版本)";
  const words = contentText.length;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* P0 (01 §3): 三级页 (项目 → 章节 → tab) 也要有完整面包屑
       *  + 顶部返回项目工作台按钮, 不能用单纯的 Link 「← 返回项目」糊弄. */}
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

          {tab === "compare" && <ChapterCompare versions={versions} />}

          {tab === "versions" && (
            <div className="card">
              <h3>所有版本 ({versions.length})</h3>
              {versions.length === 0 ? (
                <div className="muted">本章还没有任何 Agent 输出。</div>
              ) : (
                <table>
                  <thead>
                    <tr><th>类型</th><th>版本</th><th style={{ textAlign: "right" }}>分数</th><th style={{ textAlign: "right" }}>字数</th><th>时间</th><th></th></tr>
                  </thead>
                  <tbody>
                    {versions.map((v) => (
                      <tr key={v.id} className="clickable" onClick={() => setActiveVersion(v)}>
                        <td><span className="pill">{v.version_kind}</span></td>
                        <td className="mono">v{v.version_no}</td>
                        <td className="mono" style={{ textAlign: "right" }}>
                          {v.score != null ? <span className={`score-pill ${scoreClass(v.score)}`}>{v.score}</span> : "—"}
                        </td>
                        <td className="mono" style={{ textAlign: "right" }}>{v.content.length}</td>
                        <td className="muted tiny">{new Date(v.created_at).toLocaleString("zh-CN")}</td>
                        <td>{activeVersion?.id === v.id ? <span className="gold">已展示</span> : <button>查看</button>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {tab === "timeline" && (
            <div className="card">
              <h3>Agent 步骤时间线</h3>
              {steps.length === 0 ? (
                <div className="muted">本章没有记录到的步骤。运行流水线后这里会显示每个 Agent 的输入/输出。</div>
              ) : (
                <div className="timeline">
                  {steps.map((s, i) => (
                    <div key={s.id} className={`timeline-row ${s.status}`}>
                      <span className="step-no mono">{i + 1}</span>
                      <span className="step-name">{s.agent_name} · {s.step_name}</span>
                      <span className="step-meta">
                        {s.model_name ?? "—"} · {s.input_tokens}/{s.output_tokens} tok · {s.duration_ms}ms · ${s.cost_usd.toFixed(4)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {tab === "context" && (
            <div className="col gap-3">
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

function scoreClass(s: number) {
  if (s >= 80) return "pass";
  if (s >= 60) return "fail";
  return "low";
}
