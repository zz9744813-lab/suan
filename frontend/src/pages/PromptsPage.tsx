import { useEffect, useState } from "react";
import {
  listPromptTemplates, listPromptVersions, createPromptVersion, activatePromptVersion,
} from "../api";
import type { PromptTemplate, PromptVersion } from "../types";
import { PromptVersionViewer } from "../components/prompts/PromptVersionViewer";

export function PromptsPage() {
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [active, setActive] = useState<PromptTemplate | null>(null);
  const [versions, setVersions] = useState<PromptVersion[]>([]);
  const [editing, setEditing] = useState<{ body: string; note: string; activate: boolean } | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

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
    </div>
  );
}
