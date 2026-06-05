/**
 * BehaviorPage — P8 behavior-card-knowledge-base
 *
 * Three-column layout:
 *   ┌──────────────┬──────────────────────────┬──────────────┐
 *   │ Left Sidebar │ Center Card Shelf         │ Right Detail │
 *   │ Filters      │ Category shelves w/ cards │ Card detail  │
 *   │ Tags, Search │ Drag-drop categories      │ drawer       │
 *   └──────────────┴──────────────────────────┴──────────────┘
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  listBehaviorCategories,
  listBehaviorCards,
  getBehaviorCardDetail,
  moveBehaviorCard,
  archiveBehaviorCard,
  createBehaviorCard,
  updateBehaviorCard,
  collapseBehaviorCategory,
} from "../api";
import type {
  BehaviorCategoryRead,
  BehaviorCardSummary,
  BehaviorCardDetail,
} from "../api";

const ROLE_TAGS = ["主角", "女主", "反派", "配角", "热血", "理智", "隐忍", "腹黑"];
const SCENE_TAGS = ["公开羞辱", "宗门抛弃", "偶得异宝", "高人指点", "废柴逆袭", "日常", "危机"];
const STATUS_OPTIONS = [
  { value: "", label: "全部" },
  { value: "ready", label: "可注入" },
  { value: "pending_clean", label: "待清洗" },
  { value: "review_required", label: "需复核" },
  { value: "archived", label: "已归档" },
];
const SORT_OPTIONS = [
  { value: "recent", label: "最近使用" },
  { value: "fit_score", label: "适配度" },
  { value: "source_count", label: "来源热度" },
  { value: "usage_count", label: "使用次数" },
  { value: "updated_at", label: "最近更新" },
];
const STATUS_COLORS: Record<string, string> = {
  ready: "var(--state-ok)",
  high_frequency: "var(--accent-primary)",
  pending_clean: "var(--state-warn)",
  review_required: "#eab308",
  archived: "var(--text-tertiary)",
};
const STATUS_LABELS: Record<string, string> = {
  ready: "可注入",
  high_frequency: "高频",
  pending_clean: "待清洗",
  review_required: "需复核",
  archived: "已归档",
};

export function BehaviorPage() {
  // --- data ---
  const [categories, setCategories] = useState<BehaviorCategoryRead[]>([]);
  const [cards, setCards] = useState<BehaviorCardSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedCard, setSelectedCard] = useState<BehaviorCardDetail | null>(null);
  const [loading, setLoading] = useState(false);

  // --- filters ---
  const [keyword, setKeyword] = useState("");
  const [roleTags, setRoleTags] = useState<string[]>([]);
  const [sceneTags, setSceneTags] = useState<string[]>([]);
  const [status, setStatus] = useState("");
  const [categoryId, setCategoryId] = useState<number | undefined>(undefined);
  const [sort, setSort] = useState("recent");

  // --- modals ---
  const [showCreate, setShowCreate] = useState(false);

  // --- fetch categories ---
  const loadCategories = useCallback(async () => {
    const cats = await listBehaviorCategories();
    setCategories(cats ?? []);
  }, []);

  // --- fetch cards ---
  const loadCards = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listBehaviorCards({
        keyword: keyword || undefined,
        category_id: categoryId,
        role_tags: roleTags.length ? roleTags : undefined,
        scene_tags: sceneTags.length ? sceneTags : undefined,
        status: status || undefined,
        sort,
        page_size: 200,
      });
      setCards(res?.items ?? []);
      setTotal(res?.total ?? 0);
    } finally {
      setLoading(false);
    }
  }, [keyword, categoryId, roleTags, sceneTags, status, sort]);

  useEffect(() => { loadCategories(); }, [loadCategories]);
  useEffect(() => { loadCards(); }, [loadCards]);

  // --- select card ---
  const selectCard = useCallback(async (id: number) => {
    const detail = await getBehaviorCardDetail(id);
    setSelectedCard(detail ?? null);
  }, []);

  // --- archive ---
  const handleArchive = useCallback(async (id: number) => {
    await archiveBehaviorCard(id);
    setSelectedCard(null);
    loadCards();
    loadCategories();
  }, [loadCards, loadCategories]);

  // --- toggle category collapse ---
  const handleCollapse = useCallback(async (cat: BehaviorCategoryRead) => {
    await collapseBehaviorCategory(cat.id, !cat.is_collapsed);
    loadCategories();
  }, [loadCategories]);

  // --- group cards by category ---
  const cardsByCategory = useMemo(() => {
    const map = new Map<number, BehaviorCardSummary[]>();
    for (const c of cards) {
      const key = c.category_id ?? 0;
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(c);
    }
    return map;
  }, [cards]);

  return (
    <div className="page behavior-page" style={{ height: "100%", overflow: "hidden" }}>
      <div className="behavior-layout">
        {/* ====== LEFT SIDEBAR ====== */}
        <aside className="behavior-sidebar">
          <div className="behavior-sidebar-section">
            <h4>搜索</h4>
            <input
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="角色卡名称、技巧..."
              className="input"
            />
          </div>

          <div className="behavior-sidebar-section">
            <h4>人物标签</h4>
            <TagChips options={ROLE_TAGS} value={roleTags} onChange={setRoleTags} />
          </div>

          <div className="behavior-sidebar-section">
            <h4>情境标签</h4>
            <TagChips options={SCENE_TAGS} value={sceneTags} onChange={setSceneTags} />
          </div>

          <div className="behavior-sidebar-section">
            <h4>状态</h4>
            <select value={status} onChange={(e) => setStatus(e.target.value)} className="input">
              {STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>

          <div className="behavior-sidebar-section">
            <h4>排序</h4>
            <select value={sort} onChange={(e) => setSort(e.target.value)} className="input">
              {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>

          <div className="behavior-sidebar-section">
            <h4>分类</h4>
            {categories.map((cat) => (
              <div
                key={cat.id}
                className={`behavior-cat-item ${categoryId === cat.id ? "active" : ""}`}
                onClick={() => setCategoryId(categoryId === cat.id ? undefined : cat.id)}
              >
                <span>{cat.icon} {cat.name}</span>
                <span className="muted tiny">{cat.card_count}</span>
              </div>
            ))}
          </div>

          <div className="muted tiny" style={{ marginTop: "auto", padding: "8px" }}>
            共 {total} 张角色卡
            {loading ? " · 加载中…" : ""}
          </div>
        </aside>

        {/* ====== CENTER CARD SHELF ====== */}
        <main className="behavior-shelf">
          <header className="behavior-shelf-header">
            <h2>行为模式库</h2>
            <span className="muted">角色卡式人物行为知识库</span>
            <span className="spacer" />
            <button className="primary" onClick={() => setShowCreate(true)}>+ 新建角色卡</button>
          </header>

          <div className="behavior-shelf-body">
            {cards.length === 0 && !loading && (
              <div className="empty">没有匹配的角色卡。调整左侧筛选，或新建角色卡。</div>
            )}
            {categories.map((cat) => {
              const catCards = cardsByCategory.get(cat.id);
              if (!catCards || catCards.length === 0) return null;
              return (
                <div key={cat.id} className="behavior-shelf-row">
                  <div className="behavior-shelf-row-head" onClick={() => handleCollapse(cat)}>
                    <span className="behavior-shelf-caret">{cat.is_collapsed ? "▶" : "▼"}</span>
                    <span>{cat.icon} {cat.name}</span>
                    <span className="muted tiny">({catCards.length})</span>
                  </div>
                  {!cat.is_collapsed && (
                    <div className="behavior-shelf-cards">
                      {catCards.map((card) => (
                        <article
                          key={card.id}
                          className={`behavior-card ${selectedCard?.id === card.id ? "selected" : ""}`}
                          onClick={() => selectCard(card.id)}
                          draggable
                          onDragStart={(e) => {
                            e.dataTransfer.setData("text/plain", String(card.id));
                            e.dataTransfer.effectAllowed = "move";
                          }}
                        >
                          <div className="behavior-card-head">
                            <span className="behavior-card-avatar">{card.avatar_symbol || "📋"}</span>
                            <div className="behavior-card-info">
                              <b>{card.name}</b>
                              <span className="muted tiny">{card.role_type}</span>
                            </div>
                            <span
                              className="behavior-card-status"
                              style={{ color: STATUS_COLORS[card.status] ?? "var(--text-secondary)" }}
                            >
                              {STATUS_LABELS[card.status] ?? card.status}
                            </span>
                          </div>
                          {card.summary && <p className="behavior-card-summary">{card.summary}</p>}
                          {card.behavior_chain && (
                            <div className="behavior-card-chain">{card.behavior_chain}</div>
                          )}
                          <div className="behavior-card-tags">
                            {card.tags.slice(0, 4).map((t) => (
                              <span className={`chip chip-${t.tag_type}`} key={t.id}>{t.tag_name}</span>
                            ))}
                          </div>
                          <div className="behavior-card-stats">
                            <span title="适配度">★{card.fit_score.toFixed(0)}</span>
                            <span title="来源数">📚{card.source_count}</span>
                            <span title="技巧数">💡{card.technique_count}</span>
                            <span title="使用次数">🔄{card.usage_count}</span>
                          </div>
                        </article>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </main>

        {/* ====== RIGHT DETAIL DRAWER ====== */}
        <aside className={`behavior-detail ${selectedCard ? "open" : ""}`}>
          {selectedCard ? (
            <BehaviorDetailDrawer
              card={selectedCard}
              onClose={() => setSelectedCard(null)}
              onArchive={() => handleArchive(selectedCard.id)}
            />
          ) : (
            <div className="behavior-detail-empty">点击左侧角色卡查看详情</div>
          )}
        </aside>
      </div>

      {showCreate && (
        <CardEditorModal
          categories={categories}
          onClose={() => setShowCreate(false)}
          onSaved={() => { setShowCreate(false); loadCards(); loadCategories(); }}
        />
      )}
    </div>
  );
}

/* ---------- Sub-components ---------- */

function TagChips({ options, value, onChange }: {
  options: string[]; value: string[]; onChange: (v: string[]) => void;
}) {
  return (
    <div className="tag-picker">
      {options.map((o) => {
        const on = value.includes(o);
        return (
          <button key={o} className={`chip ${on ? "chip-on" : ""}`}
            onClick={() => onChange(on ? value.filter((v) => v !== o) : [...value, o])}>
            {o}
          </button>
        );
      })}
    </div>
  );
}

function BehaviorDetailDrawer({ card, onClose, onArchive }: {
  card: BehaviorCardDetail; onClose: () => void; onArchive: () => void;
}) {
  return (
    <div className="behavior-detail-inner">
      <div className="behavior-detail-head">
        <span className="behavior-card-avatar lg">{card.avatar_symbol || "📋"}</span>
        <div>
          <h3>{card.name}</h3>
          <span className="muted">{card.role_type}</span>
        </div>
        <button className="ghost" onClick={onClose}>×</button>
      </div>
      {card.summary && <p className="behavior-detail-summary">{card.summary}</p>}

      <div className="behavior-detail-actions">
        <button className="primary small">注入当前项目</button>
        <button className="ghost small">编辑</button>
        <button className="ghost small" onClick={onArchive}>归档</button>
      </div>

      {/* tags */}
      <Section title="标签与适用场景">
        <div className="behavior-detail-tags">
          {card.tags.map((t) => (
            <span className={`chip chip-${t.tag_type}`} key={t.id}>{t.tag_type}:{t.tag_name}</span>
          ))}
        </div>
        {card.suitable_scenes && <div className="kv"><span className="k">适用</span><span className="v">{card.suitable_scenes}</span></div>}
        {card.unsuitable_scenes && <div className="kv"><span className="k">不适用</span><span className="v">{card.unsuitable_scenes}</span></div>}
      </Section>

      {/* chains */}
      <Section title="行为链">
        <div className="behavior-chain-display">{card.behavior_chain || "—"}</div>
      </Section>
      <Section title="情绪链">
        <div className="behavior-chain-display">{card.emotion_chain || "—"}</div>
      </Section>
      <Section title="对白风格">
        <p>{card.dialogue_style || "—"}</p>
      </Section>

      {/* techniques */}
      <Section title={`写作技巧 (${card.techniques.length})`}>
        {card.techniques.length === 0 && <p className="muted">暂无</p>}
        {card.techniques.map((t) => (
          <div key={t.id} className="behavior-technique">
            <b>{t.title}</b>
            <p>{t.content}</p>
            {t.example && <blockquote className="quote">「{t.example}」</blockquote>}
          </div>
        ))}
      </Section>

      {/* sources */}
      <Section title={`拆书来源 (${card.sources.length})`}>
        {card.sources.length === 0 && <p className="muted">暂无来源</p>}
        {card.sources.map((s) => (
          <div key={s.id} className="behavior-source-item">
            <span>{s.book_title ?? "未知书籍"}</span>
            {s.chapter_title && <span className="muted tiny"> · {s.chapter_title}</span>}
            {s.extracted_summary && <p className="tiny">{s.extracted_summary}</p>}
            {s.confidence > 0 && <span className="muted tiny">置信度 {(s.confidence * 100).toFixed(0)}%</span>}
          </div>
        ))}
      </Section>

      {/* scores */}
      <Section title="评分">
        <div className="behavior-scores">
          <ScoreBar label="综合适配" value={card.fit_score} />
          <ScoreBar label="稳定性" value={card.stability_score} />
          <ScoreBar label="对白质量" value={card.dialogue_score} />
          <ScoreBar label="泛化能力" value={card.generalization_score} />
        </div>
      </Section>

      {/* usage */}
      {card.usage_logs.length > 0 && (
        <Section title={`调用历史 (${card.usage_logs.length})`}>
          {card.usage_logs.slice(0, 5).map((log) => (
            <div key={log.id} className="behavior-usage-row">
              <span>{log.agent_role}</span>
              <span className="muted tiny">{new Date(log.created_at).toLocaleString()}</span>
            </div>
          ))}
        </Section>
      )}

      {card.injection_hint && (
        <Section title="注入提示">
          <div className="behavior-injection-hint">{card.injection_hint}</div>
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="behavior-detail-section">
      <h4>{title}</h4>
      {children}
    </div>
  );
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="behavior-score-row">
      <span className="k">{label}</span>
      <div className="behavior-score-bar">
        <div className="behavior-score-fill" style={{ width: `${value}%` }} />
      </div>
      <span className="v">{value.toFixed(0)}</span>
    </div>
  );
}

function CardEditorModal({ categories, onClose, onSaved }: {
  categories: BehaviorCategoryRead[];
  onClose: () => void; onSaved: () => void;
}) {
  const [name, setName] = useState("");
  const [roleType, setRoleType] = useState("");
  const [summary, setSummary] = useState("");
  const [behaviorChain, setBehaviorChain] = useState("");
  const [emotionChain, setEmotionChain] = useState("");
  const [dialogueStyle, setDialogueStyle] = useState("");
  const [suitableScenes, setSuitableScenes] = useState("");
  const [unsuitableScenes, setUnsuitableScenes] = useState("");
  const [injectionHint, setInjectionHint] = useState("");
  const [categoryId, setCategoryId] = useState<number | undefined>(undefined);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await createBehaviorCard({
        name: name.trim(),
        role_type: roleType || null,
        category_id: categoryId ?? null,
        summary: summary || null,
        behavior_chain: behaviorChain || null,
        emotion_chain: emotionChain || null,
        dialogue_style: dialogueStyle || null,
        suitable_scenes: suitableScenes || null,
        unsuitable_scenes: unsuitableScenes || null,
        injection_hint: injectionHint || null,
        tags: [],
        techniques: [],
      });
      onSaved();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header>
          <h3>新建角色卡</h3>
          <button onClick={onClose}>×</button>
        </header>
        <div className="modal-body">
          <label>卡片名称 *</label>
          <input value={name} onChange={(e) => setName(e.target.value)} className="input" placeholder="如：热血逆袭男主" />
          <label>人物类型</label>
          <input value={roleType} onChange={(e) => setRoleType(e.target.value)} className="input" placeholder="主角 / 女主 / 反派 / 配角" />
          <label>分类</label>
          <select value={categoryId ?? ""} onChange={(e) => setCategoryId(e.target.value ? Number(e.target.value) : undefined)} className="input">
            <option value="">— 选择分类 —</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
          </select>
          <label>一句话概括</label>
          <input value={summary} onChange={(e) => setSummary(e.target.value)} className="input" />
          <label>行为链</label>
          <input value={behaviorChain} onChange={(e) => setBehaviorChain(e.target.value)} className="input" placeholder="沉默忍受 → 观察破绽 → 当众反问 → 用结果打脸" />
          <label>情绪链</label>
          <input value={emotionChain} onChange={(e) => setEmotionChain(e.target.value)} className="input" placeholder="压抑 → 愤怒 → 冷静 → 爆发 → 立誓" />
          <label>对白风格</label>
          <input value={dialogueStyle} onChange={(e) => setDialogueStyle(e.target.value)} className="input" />
          <label>适用场景</label>
          <input value={suitableScenes} onChange={(e) => setSuitableScenes(e.target.value)} className="input" />
          <label>不适用场景</label>
          <input value={unsuitableScenes} onChange={(e) => setUnsuitableScenes(e.target.value)} className="input" />
          <label>注入提示</label>
          <textarea value={injectionHint} onChange={(e) => setInjectionHint(e.target.value)} className="textarea" rows={2} />
        </div>
        <footer>
          <span className="spacer" />
          <button onClick={onClose}>取消</button>
          <button className="primary" onClick={save} disabled={busy || !name.trim()}>
            {busy ? "创建中…" : "创建"}
          </button>
        </footer>
      </div>
    </div>
  );
}
