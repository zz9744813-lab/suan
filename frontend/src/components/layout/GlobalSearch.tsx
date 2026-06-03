/**
 * GlobalSearch — 顶栏全局搜索 (Round 11, P0-UI-5)
 *
 * 设计要点:
 *   - 固定在主区上方, 不随页面滚动消失
 *   - 输入 ≥1 字符后 debounce 200ms 触发 /api/search
 *   - 下拉浮层展示分组结果, 键盘 ↑↓ 选择, Enter 跳转, Esc 关闭
 *   - 支持 Ctrl+K (Mac: ⌘K) 快捷键聚焦, "/" 也能聚焦
 *   - 跳转后清空 query 并关闭浮层
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { globalSearch } from "../../api";
import type { SearchResult, SearchResultType } from "../../types";
import "./GlobalSearch.css";

const TYPE_LABEL: Record<SearchResultType, string> = {
  project: "项目",
  chapter: "章节",
  character: "人物",
  foreshadow: "伏笔",
  hard_fact: "硬事实",
  study_material: "拆书",
  behavior_pattern: "行为",
};

const TYPE_ICON: Record<SearchResultType, string> = {
  project: "📁",
  chapter: "📄",
  character: "👤",
  foreshadow: "🪝",
  hard_fact: "📌",
  study_material: "📚",
  behavior_pattern: "🎭",
};

export function GlobalSearch() {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const navigate = useNavigate();

  // debounce + fetch
  useEffect(() => {
    if (!q.trim()) { setResults([]); setLoading(false); return; }
    setLoading(true);
    const id = window.setTimeout(() => {
      globalSearch(q.trim(), 30)
        .then((r) => { setResults(r); setActive(0); })
        .catch(() => { setResults([]); })
        .finally(() => setLoading(false));
    }, 200);
    return () => window.clearTimeout(id);
  }, [q]);

  // click-outside to close
  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!rootRef.current) return;
      if (!rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  // Ctrl/Cmd+K and "/" to focus
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      } else if (e.key === "/" && document.activeElement?.tagName !== "INPUT"
                 && document.activeElement?.tagName !== "TEXTAREA") {
        e.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // group results by type for visual chunking
  const grouped = useMemo(() => {
    const m: Record<string, SearchResult[]> = {};
    for (const r of results) {
      (m[r.type] ??= []).push(r);
    }
    return m;
  }, [results]);

  // flat index for keyboard nav
  const flat = useMemo(() => results, [results]);

  function highlight(text: string): React.ReactNode {
    if (!q.trim()) return text;
    const idx = text.toLowerCase().indexOf(q.toLowerCase());
    if (idx < 0) return text;
    return (
      <>
        {text.slice(0, idx)}
        <mark className="gs-hl">{text.slice(idx, idx + q.length)}</mark>
        {text.slice(idx + q.length)}
      </>
    );
  }

  function navigateTo(link: string) {
    setOpen(false);
    setQ("");
    setResults([]);
    inputRef.current?.blur();
    navigate(link);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(flat.length - 1, a + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(0, a - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const target = flat[active];
      if (target) navigateTo(target.link);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
      inputRef.current?.blur();
    }
  }

  // build a flat index lookup → for highlighting the active item
  let runningIdx = -1;

  return (
    <div className="gs-root" ref={rootRef}>
      <div className={`gs-input-wrap ${open ? "focused" : ""}`}>
        <span className="gs-icon" aria-hidden>🔍</span>
        <input
          ref={inputRef}
          className="gs-input"
          placeholder="搜项目 / 章节 / 人物 / 伏笔 / 硬事实 / 拆书 / 行为模式..."
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
        {loading && <span className="gs-spinner" aria-hidden />}
        {q && (
          <button
            className="gs-clear"
            onClick={() => { setQ(""); setResults([]); inputRef.current?.focus(); }}
            title="清空"
            aria-label="清空"
          >×</button>
        )}
        <kbd className="gs-hint">/</kbd>
      </div>

      {open && (q.trim() || loading) && (
        <div className="gs-dropdown">
          {loading && results.length === 0 && (
            <div className="gs-empty muted">搜索中…</div>
          )}
          {!loading && q.trim() && results.length === 0 && (
            <div className="gs-empty muted">
              没有匹配「{q}」的结果。
              <div className="gs-tip">试试缩短关键词,或换个字。</div>
            </div>
          )}
          {results.length > 0 && (
            <div className="gs-results">
              {Object.entries(grouped).map(([type, items]) => (
                <div key={type} className="gs-group">
                  <div className="gs-group-head">
                    <span className="gs-group-icon">{TYPE_ICON[type as SearchResultType]}</span>
                    <span className="gs-group-label">{TYPE_LABEL[type as SearchResultType]}</span>
                    <span className="muted small">{items.length}</span>
                  </div>
                  {items.map((r) => {
                    runningIdx++;
                    const idx = runningIdx;
                    return (
                      <button
                        key={`${r.type}-${r.id}`}
                        className={`gs-item ${idx === active ? "active" : ""}`}
                        onMouseEnter={() => setActive(idx)}
                        onClick={() => navigateTo(r.link)}
                      >
                        <div className="gs-item-title">{highlight(r.title)}</div>
                        {r.snippet && (
                          <div className="gs-item-snippet muted small">{highlight(r.snippet)}</div>
                        )}
                        <div className="gs-item-meta muted tiny">
                          <span>{r.link}</span>
                          <span>·</span>
                          <span>score {r.score}</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              ))}
            </div>
          )}
          <div className="gs-footer muted small">
            <span><kbd>↑</kbd><kbd>↓</kbd> 切换</span>
            <span><kbd>↵</kbd> 打开</span>
            <span><kbd>Esc</kbd> 关闭</span>
            <span className="gs-footer-spacer" />
            <span>{results.length} 个结果</span>
          </div>
        </div>
      )}
    </div>
  );
}
