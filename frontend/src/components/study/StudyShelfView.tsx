/**
 * StudyShelfView — P0 返工 Phase 3.3
 *
 * 拆书首页两屏：
 *   - 第一屏：书架 (Shelf) 网格，每一格是一组书 (例: "我的玄幻参考" / "鲁迅全集" / "未分组")
 *   - 第二屏：某书架内的书 (Book) 列表 + 详情抽屉 (点书 → BookDashboard)
 *
 * 设计原则:
 *   - 书架数据走 /api/study/shelves (含虚拟的 "未分组" shelf, id=0)
 *   - 书的列表走 /api/study/books?shelf_id=X (shelf_id=0 等于未分组)
 *   - 单书详情走 /api/study/books/{id}/dashboard (一次性聚合)
 *   - 不破坏旧 BookLibrary 逻辑 (行为模式 tab 继续用)
 */
import { useEffect, useMemo, useState } from "react";
import {
  listStudyShelves,
  createStudyShelf,
  deleteStudyShelf,
  listStudyBooks,
  getBookDashboard,
  createStudyMaterial,
} from "../../api";
import type {
  StudyShelf,
  StudyMaterial,
  StudyBookDashboard,
} from "../../types";

type View =
  | { kind: "shelves" }
  | { kind: "books"; shelf: StudyShelf }
  | { kind: "detail"; shelf: StudyShelf; bookId: number };

export function StudyShelfView() {
  const [view, setView] = useState<View>({ kind: "shelves" });
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="study-shelf-view">
      {error && (
        <div className="card error-card" role="alert">
          <div className="row">
            <b>操作失败</b>
            <span className="spacer" />
            <button onClick={() => setError(null)}>关闭</button>
          </div>
          <pre className="error-pre">{error}</pre>
        </div>
      )}

      {view.kind === "shelves" && (
        <ShelfGrid onOpen={(s) => setView({ kind: "books", shelf: s })} onError={setError} />
      )}
      {view.kind === "books" && (
        <BookList
          shelf={view.shelf}
          onBack={() => setView({ kind: "shelves" })}
          onOpenBook={(id) =>
            setView({ kind: "detail", shelf: view.shelf, bookId: id })
          }
          onError={setError}
        />
      )}
      {view.kind === "detail" && (
        <BookDetail
          shelf={view.shelf}
          bookId={view.bookId}
          onBack={() => setView({ kind: "books", shelf: view.shelf })}
          onError={setError}
        />
      )}
    </div>
  );
}

/* ===================== 第一屏：书架网格 ===================== */

function ShelfGrid(props: {
  onOpen: (s: StudyShelf) => void;
  onError: (msg: string | null) => void;
}) {
  const [shelves, setShelves] = useState<StudyShelf[]>([]);
  const [loading, setLoading] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [name, setName] = useState("");
  const [color, setColor] = useState("#a78bfa");

  const refresh = () => {
    setLoading(true);
    listStudyShelves()
      .then((r) => setShelves(r.data ?? (r as any)))
      .catch((e) => props.onError(String(e?.message ?? e)))
      .finally(() => setLoading(false));
  };
  useEffect(refresh, []);

  const onCreate = async () => {
    if (!name.trim()) {
      props.onError("书架名不能为空。");
      return;
    }
    try {
      const r = await createStudyShelf({ name, color });
      const created = (r as any).data ?? r;
      setShelves((cur) => [...cur, created]);
      setShowNew(false);
      setName("");
    } catch (e: any) {
      props.onError(String(e?.message ?? e));
    }
  };

  const onDelete = async (s: StudyShelf) => {
    if (s.id === 0) {
      props.onError("虚拟的「未分组」书架不能删。把书归到其他书架后这里就空了。");
      return;
    }
    if (!confirm(`删除书架「${s.name}」？\n里面的书不会丢，会回到「未分组」。`)) return;
    try {
      await deleteStudyShelf(s.id);
      refresh();
    } catch (e: any) {
      props.onError(String(e?.message ?? e));
    }
  };

  return (
    <div className="shelf-grid-wrap">
      <div className="row" style={{ marginBottom: 12, gap: 8 }}>
        <h2 style={{ margin: 0 }}>📚 书架</h2>
        <span className="sub" style={{ marginLeft: 8 }}>
          点开书架 → 看里面的书
        </span>
        <span className="spacer" />
        <button onClick={() => setShowNew((v) => !v)}>
          {showNew ? "取消" : "+ 新建书架"}
        </button>
      </div>

      {showNew && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="row" style={{ gap: 8 }}>
            <input
              placeholder="书架名 (例: 鲁迅全集)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              style={{ flex: 1 }}
            />
            <input
              type="color"
              value={color}
              onChange={(e) => setColor(e.target.value)}
              style={{ width: 40 }}
              title="书架颜色"
            />
            <button onClick={onCreate}>创建</button>
          </div>
        </div>
      )}

      {loading && shelves.length === 0 ? (
        <div className="card">加载中…</div>
      ) : shelves.length === 0 ? (
        <div className="card empty-card">
          <p>还没有书架。点上面的「+ 新建书架」开始整理你的参考书。</p>
        </div>
      ) : (
        <div className="shelf-grid">
          {shelves.map((s) => (
            <ShelfCard key={s.id} shelf={s} onOpen={() => props.onOpen(s)} onDelete={() => onDelete(s)} />
          ))}
        </div>
      )}
    </div>
  );
}

function ShelfCard(props: { shelf: StudyShelf; onOpen: () => void; onDelete: () => void }) {
  const { shelf } = props;
  const color = shelf.color || "#8b5cf6";
  return (
    <div
      className="shelf-card"
      onClick={props.onOpen}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && props.onOpen()}
      style={{ borderTopColor: color }}
    >
      <div className="shelf-card-head">
        <div className="shelf-card-color" style={{ background: color }} />
        <div className="shelf-card-name">{shelf.name}</div>
        <span className="spacer" />
        {shelf.id !== 0 && (
          <button
            className="shelf-card-del"
            onClick={(e) => {
              e.stopPropagation();
              props.onDelete();
            }}
            title="删除书架"
          >
            ✕
          </button>
        )}
      </div>
      {shelf.description && <div className="shelf-card-desc">{shelf.description}</div>}
      <div className="shelf-card-count">{shelf.book_count} 本</div>
      {shelf.top_genres.length > 0 && (
        <div className="shelf-card-chips">
          {shelf.top_genres.slice(0, 3).map((g) => (
            <span key={g} className="chip">{g}</span>
          ))}
          {shelf.top_tags.slice(0, 2).map((t) => (
            <span key={t} className="chip chip-soft">#{t}</span>
          ))}
        </div>
      )}
    </div>
  );
}

/* ===================== 第二屏：书架内的书 ===================== */

function BookList(props: {
  shelf: StudyShelf;
  onBack: () => void;
  onOpenBook: (id: number) => void;
  onError: (msg: string | null) => void;
}) {
  const [books, setBooks] = useState<StudyMaterial[]>([]);
  const [loading, setLoading] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [text, setText] = useState("");

  const refresh = () => {
    setLoading(true);
    listStudyBooks(props.shelf.id)
      .then((r) => setBooks(r.data ?? (r as any)))
      .catch((e) => props.onError(String(e?.message ?? e)))
      .finally(() => setLoading(false));
  };
  useEffect(refresh, [props.shelf.id]);

  const onCreatePaste = async () => {
    if (!title.trim() || !text.trim()) {
      props.onError("标题和正文都不能为空。");
      return;
    }
    try {
      await createStudyMaterial({
        title,
        author,
        raw_text: text,
        source: "paste",
        shelf_id: props.shelf.id || null,
      });
      setShowNew(false);
      setTitle("");
      setAuthor("");
      setText("");
      refresh();
    } catch (e: any) {
      props.onError(String(e?.message ?? e));
    }
  };

  return (
    <div>
      <div className="row" style={{ marginBottom: 12, gap: 8 }}>
        <button onClick={props.onBack}>← 返回书架</button>
        <h2 style={{ margin: 0, marginLeft: 8 }}>
          📖 {props.shelf.name}
        </h2>
        <span className="sub" style={{ marginLeft: 8 }}>
          {books.length} 本
        </span>
        <span className="spacer" />
        <button onClick={() => setShowNew((v) => !v)}>
          {showNew ? "取消" : "+ 加书"}
        </button>
      </div>

      {showNew && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="col" style={{ gap: 8 }}>
            <input
              placeholder="标题"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <input
              placeholder="作者 (可空)"
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
            />
            <textarea
              placeholder="把小说正文粘到这里…"
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={6}
            />
            <div className="row" style={{ gap: 8 }}>
              <span className="spacer" />
              <button onClick={onCreatePaste}>创建</button>
            </div>
          </div>
        </div>
      )}

      {loading && books.length === 0 ? (
        <div className="card">加载中…</div>
      ) : books.length === 0 ? (
        <div className="card empty-card">
          <p>这个书架还没有书。点「+ 加书」粘一段参考文。</p>
        </div>
      ) : (
        <div className="book-grid">
          {books.map((b) => (
            <BookCard
              key={b.id}
              book={b}
              accent={props.shelf.color}
              onOpen={() => props.onOpenBook(b.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function BookCard(props: {
  book: StudyMaterial;
  accent: string | null;
  onOpen: () => void;
}) {
  const { book } = props;
  const cover = book.cover_color || props.accent || "#475569";
  return (
    <div
      className="book-card"
      onClick={props.onOpen}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && props.onOpen()}
    >
      <div className="book-spine" style={{ background: cover }} />
      <div className="book-meta">
        <div className="book-title" title={book.title}>{book.title}</div>
        <div className="book-author" title={book.author || ""}>
          {book.author || "（无名作者）"}
        </div>
        <div className="book-stats">
          <span title="章节">{book.chapter_count} 章</span>
          <span title="人物">{book.character_count} 人</span>
          {book.study_quality_score != null && (
            <span title="StudyCritic 质量分">
              ★ {(book.study_quality_score * 100).toFixed(0)}
            </span>
          )}
        </div>
        {book.tags && book.tags.length > 0 && (
          <div className="book-tags">
            {book.tags.slice(0, 3).map((t) => (
              <span key={t} className="chip chip-soft">#{t}</span>
            ))}
          </div>
        )}
        {book.graph_materialized_at && (
          <div className="book-graph-ok" title="已贡献到图谱">📊 已图谱化</div>
        )}
      </div>
    </div>
  );
}

/* ===================== 第三屏：单书 dashboard ===================== */

function BookDetail(props: {
  shelf: StudyShelf;
  bookId: number;
  onBack: () => void;
  onError: (msg: string | null) => void;
}) {
  const [data, setData] = useState<StudyBookDashboard | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    getBookDashboard(props.bookId)
      .then((r) => setData(r.data ?? (r as any)))
      .catch((e) => props.onError(String(e?.message ?? e)))
      .finally(() => setLoading(false));
  }, [props.bookId]);

  if (loading || !data) {
    return (
      <div>
        <div className="row" style={{ marginBottom: 12, gap: 8 }}>
          <button onClick={props.onBack}>← 返回 {props.shelf.name}</button>
        </div>
        <div className="card">加载中…</div>
      </div>
    );
  }

  const m = data.material;
  const cover = m.cover_color || props.shelf.color || "#475569";
  return (
    <div>
      <div className="row" style={{ marginBottom: 12, gap: 8 }}>
        <button onClick={props.onBack}>← 返回 {props.shelf.name}</button>
      </div>

      <div className="book-detail-head card" style={{ borderLeft: `6px solid ${cover}` }}>
        <div className="book-detail-title">
          <h2 style={{ margin: 0 }}>{m.title}</h2>
          <div className="sub">{m.author || "（无名作者）"}</div>
        </div>
        <div className="book-detail-stats">
          <div className="stat">
            <div className="stat-num">{data.chapter_count}</div>
            <div className="stat-label">章节</div>
          </div>
          <div className="stat">
            <div className="stat-num">{data.character_count}</div>
            <div className="stat-label">人物</div>
          </div>
          <div className="stat">
            <div className="stat-num">{data.behavior_count}</div>
            <div className="stat-label">行为模式</div>
          </div>
          <div className="stat">
            <div className="stat-num">{data.foreshadow_count}</div>
            <div className="stat-label">伏笔</div>
          </div>
        </div>
      </div>

      <div className="row" style={{ gap: 12, flexWrap: "wrap", marginTop: 12 }}>
        {m.study_quality_score != null && (
          <div className="card" style={{ flex: 1, minWidth: 240 }}>
            <h3 style={{ marginTop: 0 }}>⭐ 质量分</h3>
            <div style={{ fontSize: 32, fontWeight: 700 }}>
              {(m.study_quality_score * 100).toFixed(0)}
            </div>
            <div className="sub">StudyCritic + DeepStudy 综合</div>
          </div>
        )}
        {data.latest_run && (
          <div className="card" style={{ flex: 1, minWidth: 240 }}>
            <h3 style={{ marginTop: 0 }}>🧠 DeepStudy 最近一次</h3>
            <div className="row" style={{ gap: 6 }}>
              <b>状态:</b>
              <span className={`chip ${data.latest_run.status === "succeeded" ? "chip-ok" : ""}`}>
                {data.latest_run.status}
              </span>
            </div>
            <div className="sub">
              阶段: {data.latest_run.current_stage ?? "—"}
            </div>
            <div className="sub">
              进度: {data.latest_run.processed_chapters ?? 0} / {data.latest_run.total_chapters ?? 0} 章
            </div>
            {data.latest_run.completed_at && (
              <div className="sub">完成: {data.latest_run.completed_at}</div>
            )}
          </div>
        )}
        <div className="card" style={{ flex: 1, minWidth: 240 }}>
          <h3 style={{ marginTop: 0 }}>📊 图谱</h3>
          <div className="row" style={{ gap: 6 }}>
            <b>状态:</b>
            <span className={`chip ${data.graph_materialized ? "chip-ok" : "chip-warn"}`}>
              {data.graph_materialized ? "已物化" : "未物化"}
            </span>
          </div>
          {data.graph_materialized && (
            <div className="sub">
              本书贡献: {data.graph_node_count} 节点 / 累计 {data.graph_edge_count} 边
            </div>
          )}
          {!data.graph_materialized && data.project_id != null && (
            <div className="sub">点击下方 "深度拆书" 按钮可触发 GraphMaterializer。</div>
          )}
        </div>
      </div>

      {data.quality_timeline.length > 0 && (
        <div className="card" style={{ marginTop: 12 }}>
          <h3 style={{ marginTop: 0 }}>📈 质量分时间线</h3>
          <ul style={{ paddingLeft: 18, margin: 0 }}>
            {data.quality_timeline.map((q, i) => (
              <li key={i}>
                <b>{q.kind}</b>: {(q.score * 100).toFixed(0)} 分
                {q.at && <span className="sub"> · {q.at}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
