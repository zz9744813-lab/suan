/**
 * BehaviorPage — Round E (P1-1)
 *
 * Independent full-page view of the behavior-pattern library. The
 * original Round 5 embed lived inside StudyPage as a sub-tab; this
 * gives the user a first-class surface for browsing / editing /
 * creating patterns standalone. The query API is unchanged
 * (``/api/behavior/patterns``) so existing data is reused.
 *
 * Layout:
 *   ┌────────────┬────────────────────────────────────────┐
 *   │  filters   │   pattern grid (cards, click to edit)   │
 *   │ character  │                                          │
 *   │ situation  │                                          │
 *   │ search     │                                          │
 *   │ [+ 新建]   │                                          │
 *   └────────────┴────────────────────────────────────────┘
 */
import { useEffect, useMemo, useState } from "react";
import {
  listBehaviorPatterns,
  createBehaviorPattern,
  updateBehaviorPattern,
  deleteBehaviorPattern,
} from "../api";
import type { BehaviorPattern } from "../types";

const SAMPLE_TAGS = ["主角", "女主", "反派", "热血", "理智", "隐忍", "腹黑"];
const SAMPLE_SITUATIONS = ["公开羞辱", "宗门抛弃", "偶得异宝", "高人指点", "废柴逆袭", "日常", "危机"];

export function BehaviorPage() {
  const [character, setCharacter] = useState<string[]>([]);
  const [situation, setSituation] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [patterns, setPatterns] = useState<BehaviorPattern[]>([]);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<BehaviorPattern | null>(null);
  const [showNew, setShowNew] = useState(false);

  const queryKey = useMemo(
    () => JSON.stringify({ character, situation, search }),
    [character, situation, search],
  );

  const refresh = async () => {
    setBusy(true);
    try {
      const r = await listBehaviorPatterns({
        character: character.length ? character : undefined,
        situation: situation.length ? situation : undefined,
        search: search.trim() || undefined,
        limit: 200,
      });
      setPatterns(r ?? []);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryKey]);

  return (
    <div className="page behavior-page">
      <header className="page-header">
        <h2>行为模式库</h2>
        <span className="muted">
          沉淀从拆书中学到的可复用「人物 × 情境」行为卡片，写作时由 Planner 检索。
        </span>
        <span className="spacer" />
        <button onClick={() => setShowNew(true)} className="primary">
          + 新建模式
        </button>
      </header>

      <div className="behavior-layout">
        <aside className="behavior-filters">
          <h4>按人物标签</h4>
          <TagPicker options={SAMPLE_TAGS} value={character} onChange={setCharacter} />
          <h4>按情境标签</h4>
          <TagPicker options={SAMPLE_SITUATIONS} value={situation} onChange={setSituation} />
          <h4>关键词搜索</h4>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="在 name / typical_behavior / dialogue_style 中..."
            className="input"
          />
          <div className="muted tiny" style={{ marginTop: 12 }}>
            共 {patterns.length} 条
            {busy ? " · 加载中…" : ""}
          </div>
        </aside>

        <main className="behavior-grid">
          {patterns.length === 0 && !busy && (
            <div className="empty">没有匹配的行为模式。试试调整左侧标签，或点击「+ 新建模式」。</div>
          )}
          {patterns.map((p) => (
            <article
              key={p.id}
              className="behavior-card"
              onClick={() => setEditing(p)}
            >
              <header>
                <b>{p.name}</b>
                <span className="muted tiny">conf {(p.confidence * 100).toFixed(0)}%</span>
              </header>
              <div className="tag-row">
                {(p.character_tags || []).map((t) => (
                  <span className="chip chip-char" key={`c-${t}`}>
                    {t}
                  </span>
                ))}
                {(p.situation_tags || []).map((t) => (
                  <span className="chip chip-sit" key={`s-${t}`}>
                    {t}
                  </span>
                ))}
              </div>
              {(p.typical_behavior || []).length > 0 && (
                <ul className="bullets">
                  {p.typical_behavior.slice(0, 3).map((b, i) => (
                    <li key={i}>{b}</li>
                  ))}
                </ul>
              )}
              {p.evidence?.[0] && (
                <blockquote className="quote">「{p.evidence[0]}」</blockquote>
              )}
            </article>
          ))}
        </main>
      </div>

      {(editing || showNew) && (
        <PatternEditorModal
          pattern={editing}
          onClose={() => {
            setEditing(null);
            setShowNew(false);
          }}
          onSaved={() => {
            setEditing(null);
            setShowNew(false);
            refresh();
          }}
          onDelete={editing ? async () => {
            if (!confirm(`确认删除「${editing.name}」？`)) return;
            await deleteBehaviorPattern(editing.id);
            setEditing(null);
            refresh();
          } : undefined}
        />
      )}
    </div>
  );
}

function TagPicker(props: {
  options: string[];
  value: string[];
  onChange: (v: string[]) => void;
}) {
  return (
    <div className="tag-picker">
      {props.options.map((o) => {
        const on = props.value.includes(o);
        return (
          <button
            type="button"
            key={o}
            className={`chip ${on ? "chip-on" : ""}`}
            onClick={() =>
              props.onChange(on ? props.value.filter((v) => v !== o) : [...props.value, o])
            }
          >
            {o}
          </button>
        );
      })}
    </div>
  );
}

function PatternEditorModal(props: {
  pattern: BehaviorPattern | null;
  onClose: () => void;
  onSaved: () => void;
  onDelete?: () => void;
}) {
  const isNew = !props.pattern;
  const [name, setName] = useState(props.pattern?.name ?? "");
  const [characterTags, setCharacterTags] = useState((props.pattern?.character_tags ?? []).join(", "));
  const [situationTags, setSituationTags] = useState((props.pattern?.situation_tags ?? []).join(", "));
  const [typical, setTypical] = useState((props.pattern?.typical_behavior ?? []).join("\n"));
  const [dialogue, setDialogue] = useState((props.pattern?.dialogue_style ?? []).join("\n"));
  const [scene, setScene] = useState((props.pattern?.scene_function ?? []).join("\n"));
  const [risks, setRisks] = useState((props.pattern?.risks ?? []).join("\n"));
  const [followup, setFollowup] = useState((props.pattern?.recommended_plot_followup ?? []).join("\n"));
  const [evidence, setEvidence] = useState((props.pattern?.evidence ?? []).join("\n"));
  const [confidence, setConfidence] = useState(props.pattern?.confidence ?? 0.5);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!name.trim()) return;
    setBusy(true);
    const body = {
      name: name.trim(),
      character_tags: characterTags.split(",").map((s) => s.trim()).filter(Boolean),
      situation_tags: situationTags.split(",").map((s) => s.trim()).filter(Boolean),
      typical_behavior: typical.split("\n").map((s) => s.trim()).filter(Boolean),
      dialogue_style: dialogue.split("\n").map((s) => s.trim()).filter(Boolean),
      scene_function: scene.split("\n").map((s) => s.trim()).filter(Boolean),
      risks: risks.split("\n").map((s) => s.trim()).filter(Boolean),
      recommended_plot_followup: followup.split("\n").map((s) => s.trim()).filter(Boolean),
      evidence: evidence.split("\n").map((s) => s.trim()).filter(Boolean),
      confidence,
    };
    try {
      if (isNew) {
        await createBehaviorPattern(body);
      } else if (props.pattern) {
        await updateBehaviorPattern(props.pattern.id, body);
      }
      props.onSaved();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={props.onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header>
          <h3>{isNew ? "新建行为模式" : `编辑：${props.pattern?.name}`}</h3>
          <button onClick={props.onClose}>×</button>
        </header>
        <div className="modal-body">
          <label>模式名 *</label>
          <input value={name} onChange={(e) => setName(e.target.value)} className="input" />
          <label>人物标签（逗号分隔）</label>
          <input value={characterTags} onChange={(e) => setCharacterTags(e.target.value)} className="input" />
          <label>情境标签（逗号分隔）</label>
          <input value={situationTags} onChange={(e) => setSituationTags(e.target.value)} className="input" />
          <label>典型行为（每行一条）</label>
          <textarea value={typical} onChange={(e) => setTypical(e.target.value)} rows={3} className="textarea" />
          <label>对白风格（每行一条）</label>
          <textarea value={dialogue} onChange={(e) => setDialogue(e.target.value)} rows={3} className="textarea" />
          <label>场景功能（每行一条）</label>
          <textarea value={scene} onChange={(e) => setScene(e.target.value)} rows={3} className="textarea" />
          <label>风险（每行一条）</label>
          <textarea value={risks} onChange={(e) => setRisks(e.target.value)} rows={2} className="textarea" />
          <label>推荐后续（每行一条）</label>
          <textarea value={followup} onChange={(e) => setFollowup(e.target.value)} rows={2} className="textarea" />
          <label>证据原文（每行一条）</label>
          <textarea value={evidence} onChange={(e) => setEvidence(e.target.value)} rows={2} className="textarea" />
          <label>置信度 {Math.round(confidence * 100)}%</label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={confidence}
            onChange={(e) => setConfidence(parseFloat(e.target.value))}
          />
        </div>
        <footer>
          <span className="spacer" />
          {props.onDelete && (
            <button className="danger" onClick={props.onDelete}>
              删除
            </button>
          )}
          <button onClick={props.onClose}>取消</button>
          <button className="primary" onClick={save} disabled={busy || !name.trim()}>
            {busy ? "保存中…" : "保存"}
          </button>
        </footer>
      </div>
    </div>
  );
}
