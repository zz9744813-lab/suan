/**
 * MemoryPage — 知识库 (P0-MEM-1, Round 9)
 *
 * 3 个 tab:
 *   人物    MemoryCharacter    增/改/删
 *   伏笔    MemoryForeshadow   增/改/删 + 一键标记 paid_off / dropped
 *   硬事实  MemoryHardFact     增/删
 *
 * 项目上下文: 默认 currentProjectId, 也可 ?project=N 覆盖
 *
 * 没有"自动从章节抽取"的功能 — 那是 LLM 干的事, 这里只让用户
 * 维护 MemoryUpdate Agent 写入的知识条目。
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  listCharacters, createCharacter, deleteCharacter,
  listForeshadows, createForeshadow, updateForeshadow, deleteForeshadow,
  listHardFacts, createHardFact, deleteHardFact,
} from "../api";
import type {
  MemoryCharacter, MemoryForeshadow, MemoryHardFact,
} from "../types";
import { useProjectStore } from "../stores/projectStore";
import "./MemoryPage.css";

type Tab = "characters" | "foreshadows" | "facts";

export function MemoryPage() {
  const [params] = useSearchParams();
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const projectId = Number(params.get("project") ?? currentProjectId ?? 0);
  const [tab, setTab] = useState<Tab>("characters");
  const [reload, setReload] = useState(0);

  if (!projectId) {
    return (
      <div className="page memory-page">
        <div className="page-empty">
          <span className="muted">请先在「项目」页选一个项目。</span>
        </div>
      </div>
    );
  }

  return (
    <div className="page memory-page">
      <div className="subheader">
        <h2 className="serif">记忆库 (旧版)</h2>
        <span className="muted small">当前项目 #{projectId} · 旧 MemoryUpdate Agent 写入 (Round 9) · 推荐用 <a href="/memory">项目记忆库</a> (P3)</span>
      </div>
      <div className="tabs" style={{ padding: "0 24px" }}>
        <button className={`tab ${tab === "characters" ? "active" : ""}`} onClick={() => setTab("characters")}>人物</button>
        <button className={`tab ${tab === "foreshadows" ? "active" : ""}`} onClick={() => setTab("foreshadows")}>伏笔</button>
        <button className={`tab ${tab === "facts" ? "active" : ""}`} onClick={() => setTab("facts")}>硬事实</button>
      </div>
      <div className="memory-tab-body">
        {tab === "characters" && <CharactersTab projectId={projectId} key={`c-${reload}`} />}
        {tab === "foreshadows" && <ForeshadowsTab projectId={projectId} key={`f-${reload}`} />}
        {tab === "facts" && <HardFactsTab projectId={projectId} key={`h-${reload}`} />}
      </div>
    </div>
  );
}

// ===== 人物 =====

function CharactersTab({ projectId }: { projectId: number }) {
  const [items, setItems] = useState<MemoryCharacter[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  useEffect(() => {
    listCharacters(projectId).then((d) => { setItems(d); setLoading(false); }).catch(() => setLoading(false));
  }, [projectId]);

  async function refresh() { setItems(await listCharacters(projectId)); }

  return (
    <div className="memory-tab">
      <div className="memory-toolbar">
        <span className="muted small">{items.length} 位人物</span>
        <button className="primary" onClick={() => { setEditingId(null); setShowForm(true); }}>+ 新建人物</button>
      </div>
      {showForm && (
        <CharacterForm
          projectId={projectId}
          existing={items.find((c) => c.id === editingId) ?? null}
          onClose={() => { setShowForm(false); setEditingId(null); }}
          onSaved={async () => { setShowForm(false); setEditingId(null); await refresh(); }}
        />
      )}
      {loading ? <div className="muted">加载…</div> : items.length === 0 ? (
        <div className="muted small">还没有人物。点右上角「+ 新建人物」添加第一位。</div>
      ) : (
        <div className="character-grid">
          {items.map((c) => (
            <CharacterCard
              key={c.id}
              c={c}
              onEdit={() => { setEditingId(c.id); setShowForm(true); }}
              onDelete={async () => { if (confirm(`删除「${c.name}」?`)) { await deleteCharacter(c.id); await refresh(); } }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function CharacterCard({ c, onEdit, onDelete }: { c: MemoryCharacter; onEdit: () => void; onDelete: () => void }) {
  return (
    <div className="character-card">
      <div className="cc-head">
        <div className="cc-avatar">{c.name.slice(0, 1)}</div>
        <div className="cc-meta">
          <div className="cc-name">{c.name}</div>
          <div className="cc-role">
            <span className="pill">{roleLabel(c.role)}</span>
            {c.aliases && c.aliases.length > 0 && (
              <span className="muted small">又名 {c.aliases.join("、")}</span>
            )}
          </div>
        </div>
        <div className="cc-actions">
          <button className="link" onClick={onEdit}>编辑</button>
          <button className="link bad" onClick={onDelete}>删除</button>
        </div>
      </div>
      {c.tags && c.tags.length > 0 && (
        <div className="cc-tags">
          {c.tags.map((t) => <span key={t} className="tag">{t}</span>)}
        </div>
      )}
      {Object.keys(c.base_profile || {}).length > 0 && (
        <div className="cc-profile">
          {Object.entries(c.base_profile).map(([k, v]) => (
            <div key={k} className="profile-row">
              <span className="muted small">{k}</span>
              <span>{Array.isArray(v) ? v.join("、") : String(v)}</span>
            </div>
          ))}
        </div>
      )}
      {c.latest_state && (
        <div className="cc-latest">
          <div className="latest-title">最近状态 · 第 {c.latest_state.chapter_no} 章</div>
          {c.latest_state.current_location && <div>📍 {c.latest_state.current_location}</div>}
          {c.latest_state.current_goal && <div>🎯 {c.latest_state.current_goal}</div>}
          {c.latest_state.injury_state && <div>🤕 {c.latest_state.injury_state}</div>}
          {c.latest_state.emotion_state && <div>💢 {c.latest_state.emotion_state}</div>}
        </div>
      )}
    </div>
  );
}

function CharacterForm({ projectId, existing, onClose, onSaved }: {
  projectId: number; existing: MemoryCharacter | null; onClose: () => void; onSaved: () => void;
}) {
  const [name, setName] = useState(existing?.name ?? "");
  const [role, setRole] = useState(existing?.role ?? "support");
  const [aliases, setAliases] = useState((existing?.aliases ?? []).join("、"));
  const [tags, setTags] = useState((existing?.tags ?? []).join("、"));
  const [profileJson, setProfileJson] = useState(
    existing?.base_profile ? JSON.stringify(existing.base_profile, null, 0) : "{}"
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    let profile: Record<string, any> = {};
    try { profile = profileJson.trim() ? JSON.parse(profileJson) : {}; }
    catch (e: any) { setErr(`base_profile 不是合法 JSON: ${e.message}`); return; }
    setBusy(true); setErr(null);
    try {
      const body = {
        name, role,
        aliases: aliases.split(/[、,，]/).map((s) => s.trim()).filter(Boolean),
        tags: tags.split(/[、,，]/).map((s) => s.trim()).filter(Boolean),
        base_profile: profile,
      };
      if (existing) {
        await fetch(`/api/memory/characters/${existing.id}`, {
          method: "PATCH", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      } else {
        await createCharacter(projectId, body);
      }
      onSaved();
    } catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="memory-form">
      <div className="form-grid">
        <div className="field">
          <label>姓名 *</label>
          <input value={name} onChange={(e) => setName(e.target.value)} disabled={busy} />
        </div>
        <div className="field">
          <label>角色</label>
          <select value={role} onChange={(e) => setRole(e.target.value)} disabled={busy}>
            <option value="protagonist">主角</option>
            <option value="heroine">女主</option>
            <option value="villain">反派</option>
            <option value="support">配角</option>
            <option value="antagonist">对手</option>
            <option value="mentor">师父</option>
            <option value="other">其他</option>
          </select>
        </div>
        <div className="field span-2">
          <label>别名 (顿号或逗号分隔)</label>
          <input value={aliases} onChange={(e) => setAliases(e.target.value)} disabled={busy} />
        </div>
        <div className="field span-2">
          <label>标签 (顿号或逗号分隔)</label>
          <input value={tags} onChange={(e) => setTags(e.target.value)} disabled={busy} />
        </div>
        <div className="field span-2">
          <label>基础档案 (JSON, 例: {`{"age":18,"faction":"青云宗"}`})</label>
          <textarea value={profileJson} onChange={(e) => setProfileJson(e.target.value)} rows={3} disabled={busy} />
        </div>
      </div>
      {err && <div className="error">{err}</div>}
      <div className="form-actions">
        <button onClick={onClose} disabled={busy}>取消</button>
        <button className="primary" onClick={save} disabled={busy || !name.trim()}>
          {busy ? "保存中..." : (existing ? "保存" : "创建")}
        </button>
      </div>
    </div>
  );
}

// ===== 伏笔 =====

function ForeshadowsTab({ projectId }: { projectId: number }) {
  const [items, setItems] = useState<MemoryForeshadow[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    listForeshadows(projectId).then((d) => { setItems(d); setLoading(false); }).catch(() => setLoading(false));
  }, [projectId]);
  async function refresh() { setItems(await listForeshadows(projectId)); }

  const active = items.filter((f) => f.status === "active");
  const paid = items.filter((f) => f.status === "paid_off");
  const dropped = items.filter((f) => f.status === "dropped");

  return (
    <div className="memory-tab">
      <div className="memory-toolbar">
        <span className="muted small">{active.length} 条进行中 · {paid.length} 已回收 · {dropped.length} 已弃用</span>
        <button className="primary" onClick={() => setShowForm((v) => !v)}>{showForm ? "收起" : "+ 新建伏笔"}</button>
      </div>
      {showForm && (
        <ForeshadowForm projectId={projectId} onClose={() => setShowForm(false)} onSaved={async () => { setShowForm(false); await refresh(); }} />
      )}
      {loading ? <div className="muted">加载…</div> : items.length === 0 ? (
        <div className="muted small">还没有伏笔。</div>
      ) : (
        <div className="foreshadow-list">
          {items.map((f) => (
            <ForeshadowCard
              key={f.id}
              f={f}
              onMark={async (status, chapterNo) => {
                await updateForeshadow(f.id, {
                  status,
                  ...(status === "paid_off"
                    ? { actual_payoff_chapter: chapterNo }
                    : f.actual_payoff_chapter != null
                    ? { actual_payoff_chapter: f.actual_payoff_chapter }
                    : {}),
                });
                await refresh();
              }}
              onDelete={async () => { if (confirm(`删除伏笔「${f.name}」?`)) { await deleteForeshadow(f.id); await refresh(); } }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ForeshadowCard({ f, onMark, onDelete }: {
  f: MemoryForeshadow;
  onMark: (status: "paid_off" | "dropped" | "active", chapterNo: number) => void | Promise<void>;
  onDelete: () => void;
}) {
  const [payoffChap, setPayoffChap] = useState<number>(f.actual_payoff_chapter ?? 0);
  return (
    <div className={`foreshadow-card status-${f.status}`}>
      <div className="fc-head">
        <div>
          <div className="fc-name">{f.name}</div>
          {f.summary && <div className="fc-summary">{f.summary}</div>}
        </div>
        <div className="fc-actions">
          <span className={`pill ${f.status}`}>{statusLabel(f.status)}</span>
          <button className="link bad" onClick={onDelete}>删除</button>
        </div>
      </div>
      <div className="fc-meta">
        <div>
          <span className="muted small">埋设</span>
          <span className="mono">{f.planted_chapter ?? "—"}</span>
        </div>
        <div>
          <span className="muted small">预计回收</span>
          <span className="mono">{f.expected_payoff_chapter ?? "—"}</span>
        </div>
        <div>
          <span className="muted small">实际回收</span>
          <span className="mono">{f.actual_payoff_chapter ?? "—"}</span>
        </div>
        <div className="imp-cell">
          <span className="muted small">重要性</span>
          <div className="imp-bar">
            <div className="imp-fill" style={{ width: `${Math.round(f.importance * 100)}%` }} />
          </div>
          <span className="mono">{f.importance.toFixed(2)}</span>
        </div>
      </div>
      {f.related_characters && f.related_characters.length > 0 && (
        <div className="fc-related">
          <span className="muted small">人物:</span>
          {f.related_characters.map((r) => <span key={r} className="tag">{r}</span>)}
        </div>
      )}
      {f.related_items && f.related_items.length > 0 && (
        <div className="fc-related">
          <span className="muted small">物品:</span>
          {f.related_items.map((r) => <span key={r} className="tag">{r}</span>)}
        </div>
      )}
      {f.status === "active" && (
        <div className="fc-mark">
          <input
            type="number" min={1} placeholder="实际回收章号"
            value={payoffChap || ""}
            onChange={(e) => setPayoffChap(Number(e.target.value))}
            style={{ width: 100 }}
          />
          <button
            className="primary"
            disabled={!payoffChap}
            onClick={() => onMark("paid_off", payoffChap)}
          >
            标记已回收
          </button>
          <button onClick={() => onMark("dropped", payoffChap)}>标记弃用</button>
          <button onClick={() => onMark("active", payoffChap)}>恢复进行中</button>
        </div>
      )}
    </div>
  );
}

function ForeshadowForm({ projectId, onClose, onSaved }: {
  projectId: number; onClose: () => void; onSaved: () => void;
}) {
  const [name, setName] = useState("");
  const [summary, setSummary] = useState("");
  const [planted, setPlanted] = useState<number | "">("");
  const [expected, setExpected] = useState<number | "">("");
  const [importance, setImportance] = useState(0.5);
  const [chars, setChars] = useState("");
  const [items, setItems] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    setBusy(true); setErr(null);
    try {
      await createForeshadow(projectId, {
        name, summary,
        planted_chapter: planted === "" ? undefined : Number(planted),
        expected_payoff_chapter: expected === "" ? undefined : Number(expected),
        importance,
        related_characters: chars.split(/[、,，]/).map((s) => s.trim()).filter(Boolean),
        related_items: items.split(/[、,，]/).map((s) => s.trim()).filter(Boolean),
      });
      onSaved();
    } catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="memory-form">
      <div className="form-grid">
        <div className="field span-2">
          <label>伏笔名 *</label>
          <input value={name} onChange={(e) => setName(e.target.value)} disabled={busy} />
        </div>
        <div className="field span-2">
          <label>概要</label>
          <textarea value={summary} onChange={(e) => setSummary(e.target.value)} rows={2} disabled={busy} />
        </div>
        <div className="field">
          <label>埋设章号</label>
          <input type="number" min={1} value={planted} onChange={(e) => setPlanted(e.target.value === "" ? "" : Number(e.target.value))} disabled={busy} />
        </div>
        <div className="field">
          <label>预计回收章号</label>
          <input type="number" min={1} value={expected} onChange={(e) => setExpected(e.target.value === "" ? "" : Number(e.target.value))} disabled={busy} />
        </div>
        <div className="field span-2">
          <label>重要性 (0~1)</label>
          <input type="range" min={0} max={1} step={0.05} value={importance} onChange={(e) => setImportance(Number(e.target.value))} disabled={busy} />
          <span className="mono small">{importance.toFixed(2)}</span>
        </div>
        <div className="field span-2">
          <label>相关人物 (顿号分隔)</label>
          <input value={chars} onChange={(e) => setChars(e.target.value)} disabled={busy} />
        </div>
        <div className="field span-2">
          <label>相关物品 (顿号分隔)</label>
          <input value={items} onChange={(e) => setItems(e.target.value)} disabled={busy} />
        </div>
      </div>
      {err && <div className="error">{err}</div>}
      <div className="form-actions">
        <button onClick={onClose} disabled={busy}>取消</button>
        <button className="primary" onClick={save} disabled={busy || !name.trim()}>
          {busy ? "保存中..." : "创建"}
        </button>
      </div>
    </div>
  );
}

// ===== 硬事实 =====

function HardFactsTab({ projectId }: { projectId: number }) {
  const [items, setItems] = useState<MemoryHardFact[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    listHardFacts(projectId).then((d) => { setItems(d); setLoading(false); }).catch(() => setLoading(false));
  }, [projectId]);
  async function refresh() { setItems(await listHardFacts(projectId)); }

  return (
    <div className="memory-tab">
      <div className="memory-toolbar">
        <span className="muted small">{items.length} 条硬事实</span>
        <button className="primary" onClick={() => setShowForm((v) => !v)}>{showForm ? "收起" : "+ 新建硬事实"}</button>
      </div>
      {showForm && (
        <HardFactForm projectId={projectId} onClose={() => setShowForm(false)} onSaved={async () => { setShowForm(false); await refresh(); }} />
      )}
      {loading ? <div className="muted">加载…</div> : items.length === 0 ? (
        <div className="muted small">还没有硬事实。这是用来记录"绝不能矛盾"的设定 (如: 主角的师傅叫张三, 不能后面又改叫李四)。</div>
      ) : (
        <div className="hardfact-list">
          {items.map((f) => (
            <div key={f.id} className="hardfact-row">
              <div className="hf-meta">
                <span className="pill">{f.category}</span>
                {f.source_chapter && <span className="muted small">第 {f.source_chapter} 章</span>}
                <span className="muted tiny">{new Date(f.created_at).toLocaleString("zh-CN")}</span>
              </div>
              <div className="hf-fact">{f.fact}</div>
              <button className="link bad" onClick={async () => { if (confirm("删除此条?")) { await deleteHardFact(f.id); await refresh(); } }}>删除</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function HardFactForm({ projectId, onClose, onSaved }: {
  projectId: number; onClose: () => void; onSaved: () => void;
}) {
  const [category, setCategory] = useState("setting");
  const [fact, setFact] = useState("");
  const [source, setSource] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    setBusy(true); setErr(null);
    try {
      await createHardFact(projectId, {
        category, fact,
        source_chapter: source === "" ? undefined : Number(source),
      });
      onSaved();
    } catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="memory-form">
      <div className="form-grid">
        <div className="field">
          <label>分类</label>
          <select value={category} onChange={(e) => setCategory(e.target.value)} disabled={busy}>
            <option value="setting">设定</option>
            <option value="character">人物</option>
            <option value="event">事件</option>
            <option value="item">物品</option>
            <option value="location">地点</option>
            <option value="rule">规则</option>
            <option value="other">其他</option>
          </select>
        </div>
        <div className="field">
          <label>来源章号 (可选)</label>
          <input type="number" min={1} value={source} onChange={(e) => setSource(e.target.value === "" ? "" : Number(e.target.value))} disabled={busy} />
        </div>
        <div className="field span-2">
          <label>事实 *</label>
          <textarea value={fact} onChange={(e) => setFact(e.target.value)} rows={3} disabled={busy} placeholder="例: 主角林萧的师傅叫玄青子, 玄青子有六名亲传弟子" />
        </div>
      </div>
      {err && <div className="error">{err}</div>}
      <div className="form-actions">
        <button onClick={onClose} disabled={busy}>取消</button>
        <button className="primary" onClick={save} disabled={busy || !fact.trim()}>
          {busy ? "保存中..." : "创建"}
        </button>
      </div>
    </div>
  );
}

// ---- 辅助 ----

function roleLabel(r: string): string {
  return ({
    protagonist: "主角", heroine: "女主", villain: "反派", support: "配角",
    antagonist: "对手", mentor: "师父", other: "其他",
  } as Record<string, string>)[r] ?? r;
}
function statusLabel(s: string): string {
  return ({ active: "进行中", paid_off: "已回收", dropped: "已弃用" } as Record<string, string>)[s] ?? s;
}
