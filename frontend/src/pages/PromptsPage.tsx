import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  listPromptTemplates, listPromptVersions, createPromptVersion, activatePromptVersion,
  createPromptTemplate, deletePromptTemplate, getTemplateUsage,
} from "../api";
import type { PromptTemplate, PromptVersion } from "../types";
import { PromptVersionViewer } from "../components/prompts/PromptVersionViewer";

export function PromptsPage() {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [active, setActive] = useState<PromptTemplate | null>(null);
  const [versions, setVersions] = useState<PromptVersion[]>([]);
  const [editing, setEditing] = useState<{ body: string; note: string; activate: boolean } | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newTpl, setNewTpl] = useState({ template_key: "", name: "", category: "writing", role: "Draft", genre: "", initial_body: "" });

  useEffect(() => { listPromptTemplates().then(setTemplates).catch(() => {}); }, []);

  const pickTemplate = async (t: PromptTemplate) => {
    setActive(t);
    const v = await listPromptVersions(t.id);
    setVersions(v);
    setEditing(null);
    setSelectedVersionId(null);
  };

  const onSaveNewVersion = async () => {
    if (!active || !editing) return;
    setBusy(true);
    try {
      const v = await createPromptVersion(active.id, {
        body: editing.body,
        activate: editing.activate,
        change_note: editing.note,
      });
      setVersions([v, ...versions]);
      setEditing(null);
      setSelectedVersionId(v.id);
    } catch (e: any) { alert(e.message); }
    finally { setBusy(false); }
  };

  const onActivate = async (vid: number) => {
    if (!active) return;
    const updated = await activatePromptVersion(active.id, vid);
    setVersions(versions.map((v) => v.id === vid ? updated : { ...v, status: "deprecated" }));
  };

  // group by category
  const byCategory: Record<string, PromptTemplate[]> = {};
  for (const t of templates) {
    (byCategory[t.category] ??= []).push(t);
  }

  const selectedVersion = versions.find((v) => v.id === selectedVersionId) ?? null;
  const activeVersion = versions.find((v) => v.status === "active") ?? null;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", height: "100%", minHeight: 0 }}>
      <aside className="card" style={{ margin: 16, overflow: "auto", borderRadius: 6 }}>
        <h3 style={{ margin: "0 0 12px" }}>Prompt 模板</h3>
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <button className="btn btn-sm" onClick={() => setShowCreate(true)} title="新建模板">+ 新建</button>
          <button className="btn btn-sm" onClick={() => navigate("/prompts-matrix")} title="类型矩阵">▦ 矩阵</button>
        </div>
        {Object.entries(byCategory).map(([cat, items]) => (
          <div key={cat} style={{ marginBottom: 16 }}>
            <div className="muted tiny" style={{ textTransform: "uppercase", letterSpacing: 1, marginBottom: 6 }}>{cat}</div>
            {items.map((t) => (
              <button
                key={t.id}
                onClick={() => pickTemplate(t)}
                style={{
                  display: "block", width: "100%", textAlign: "left",
                  padding: "8px 10px", marginBottom: 4,
                  borderColor: active?.id === t.id ? "var(--accent-gold-dim)" : undefined,
                  background: active?.id === t.id ? "rgba(201, 162, 91, 0.08)" : undefined,
                }}
              >
                <div style={{ fontSize: 13 }}>{t.name}</div>
                <div className="muted tiny">{t.template_key} · {t.category}</div>
              </button>
            ))}
          </div>
        ))}
      </aside>

      <main style={{ overflow: "auto", padding: 16 }}>
        {!active ? (
          <div className="page-empty">
            <div className="big">Prompt 模板中心</div>
            <div>选择左侧任意模板查看版本、起草新版本、或激活某个版本。</div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div className="page-header">
              <div>
                <h1>{active.name}</h1>
                <div className="sub">
                  <code>{active.template_key}</code> · 角色 {active.role} · 作用域 {active.scope}
                </div>
              </div>
              <div className="actions">
                <button className="primary" onClick={() => setEditing({
                  body: versions[0]?.body ?? "",
                  note: "",
                  activate: false,
                })}>+ 起草新版本</button>
              </div>
            </div>

            {active.description && (
              <div className="card">
                <h3>说明</h3>
                <div className="muted">{active.description}</div>
                {active.hard_rules.length > 0 && (
                  <div style={{ marginTop: 8 }}>
                    <div className="muted tiny" style={{ marginBottom: 4 }}>硬规则：</div>
                    <ul style={{ margin: 0, paddingLeft: 20, fontSize: 12 }}>
                      {active.hard_rules.map((r, i) => <li key={i}>{r}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            )}

            <div className="card">
              <h3>
                版本历史 ({versions.length})
                {selectedVersion && (
                  <span className="muted small" style={{ marginLeft: 12, fontWeight: 400 }}>
                    · 已选 v{selectedVersion.version} {selectedVersion.status === "active" && "· 当前激活"}
                  </span>
                )}
              </h3>
              {versions.length === 0 ? (
                <div className="muted">还没有版本。</div>
              ) : (
                <table>
                  <thead>
                    <tr><th>版本</th><th>状态</th><th>说明</th><th>统计</th><th></th></tr>
                  </thead>
                  <tbody>
                    {versions.map((v) => (
                      <tr
                        key={v.id}
                        onClick={() => setSelectedVersionId(v.id)}
                        style={{
                          cursor: "pointer",
                          background: selectedVersionId === v.id ? "rgba(201, 162, 91, 0.1)" : undefined,
                        }}
                      >
                        <td className="mono">v{v.version}</td>
                        <td><span className={`pill ${v.status === "active" ? "succeeded" : v.status === "candidate" ? "pending" : "stopped"}`}>{v.status}</span></td>
                        <td className="muted small">{v.change_note ?? "—"}</td>
                        <td className="mono muted tiny">通过率 {(v.test_pass_rate * 100).toFixed(1)}% · 调用 {v.usage_count}</td>
                        <td onClick={(e) => e.stopPropagation()}>
                          {v.status !== "active" && (
                            <button onClick={() => onActivate(v.id)}>激活</button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {versions.length > 0 && !selectedVersion && (
                <div className="muted small" style={{ marginTop: 8 }}>
                  👆 点表格里任一行查看该版本正文,或与当前激活版本对比。
                </div>
              )}
            </div>

            {selectedVersion && (
              <PromptVersionViewer
                version={selectedVersion}
                activeVersion={activeVersion}
                onClose={() => setSelectedVersionId(null)}
              />
            )}

            {editing && (
              <div className="card">
                <h3>起草新版本</h3>
                <label>说明</label>
                <input
                  value={editing.note}
                  onChange={(e) => setEditing({ ...editing, note: e.target.value })}
                  placeholder="本次修改的内容"
                />
                <label style={{ marginTop: 8 }}>Prompt 正文</label>
                <textarea
                  value={editing.body}
                  onChange={(e) => setEditing({ ...editing, body: e.target.value })}
                  rows={20}
                  style={{ minHeight: 360, fontFamily: "var(--font-mono)" }}
                />
                <div className="row" style={{ marginTop: 8 }}>
                  <label className="row" style={{ marginBottom: 0 }}>
                    <input
                      type="checkbox"
                      checked={editing.activate}
                      onChange={(e) => setEditing({ ...editing, activate: e.target.checked })}
                      style={{ width: "auto" }}
                    />
                    <span style={{ marginLeft: 6 }}>保存后立即激活（其他版本会被标记为 deprecated）</span>
                  </label>
                  <span className="spacer" />
                  <button onClick={() => setEditing(null)}>取消</button>
                  <button className="primary" onClick={onSaveNewVersion} disabled={busy}>
                    {busy ? "保存中…" : "保存为新版本"}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </main>

      {/* P7: New template creation dialog */}
      {showCreate && (
        <div style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div className="card" style={{ width: 520, maxHeight: "90vh", overflow: "auto", padding: 24 }}>
            <h3 style={{ margin: "0 0 16px" }}>新建 Prompt 模板</h3>
            <label>名称</label>
            <input value={newTpl.name} onChange={(e) => setNewTpl({ ...newTpl, name: e.target.value, template_key: e.target.value.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "") })} placeholder="都市爽文流·写手" />
            <label>Key</label>
            <input value={newTpl.template_key} onChange={(e) => setNewTpl({ ...newTpl, template_key: e.target.value })} placeholder="drafter_urban_smooth" />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div>
                <label>分类</label>
                <select value={newTpl.category} onChange={(e) => setNewTpl({ ...newTpl, category: e.target.value })}>
                  <option value="writing">writing</option>
                  <option value="review">review</option>
                  <option value="study">study</option>
                  <option value="memory">memory</option>
                  <option value="chief">chief</option>
                </select>
              </div>
              <div>
                <label>角色</label>
                <select value={newTpl.role} onChange={(e) => setNewTpl({ ...newTpl, role: e.target.value })}>
                  <option value="Draft">Draft</option>
                  <option value="Planner">Planner</option>
                  <option value="Critic">Critic</option>
                  <option value="Rewrite">Rewrite</option>
                  <option value="Continuity">Continuity</option>
                  <option value="MemoryUpdate">MemoryUpdate</option>
                </select>
              </div>
            </div>
            <label>类型 (genre)</label>
            <select value={newTpl.genre} onChange={(e) => setNewTpl({ ...newTpl, genre: e.target.value })}>
              <option value="">通用</option>
              <option value="玄幻">玄幻</option>
              <option value="都市">都市</option>
              <option value="科幻">科幻</option>
              <option value="历史">历史</option>
              <option value="悬疑">悬疑</option>
              <option value="言情">言情</option>
            </select>
            <label>初始正文</label>
            <textarea value={newTpl.initial_body} onChange={(e) => setNewTpl({ ...newTpl, initial_body: e.target.value })} rows={10} style={{ fontFamily: "var(--font-mono)" }} placeholder="你是一位专注于…的写手…" />
            <div className="row" style={{ marginTop: 12 }}>
              <button onClick={() => setShowCreate(false)}>取消</button>
              <span className="spacer" />
              <button className="primary" onClick={async () => {
                if (!newTpl.template_key || !newTpl.name) { alert("Key 和名称必填"); return; }
                try {
                  const tpl = await createPromptTemplate({
                    template_key: newTpl.template_key,
                    name: newTpl.name,
                    category: newTpl.category,
                    role: newTpl.role,
                    genre: newTpl.genre || null,
                    initial_body: newTpl.initial_body,
                  });
                  setTemplates([...templates, tpl]);
                  setShowCreate(false);
                  setNewTpl({ template_key: "", name: "", category: "writing", role: "Draft", genre: "", initial_body: "" });
                  pickTemplate(tpl);
                } catch (e: any) { alert(e.message || "创建失败"); }
              }}>创建</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
