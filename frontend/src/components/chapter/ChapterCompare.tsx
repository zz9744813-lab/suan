/**
 * ChapterCompare — 章节版本对比视图(README 下一步 P0-UI-4)
 *
 * 用法: <ChapterCompare versions={versions} />
 *
 * 三个模式:
 *   - "side-by-side" (默认): 段落对齐的双栏, 同步滚动
 *   - "unified":           单栏 unified diff, 删除 +插入 一起看
 *   - "raw":               不算 diff, 就是两栏原始稿纸
 *
 * Diff 算法: 段落级 LCS(longest common subsequence)。中文散文的最小语义
 * 单位是句/段, 不需要也不适合做 char-level diff。
 */
import { useMemo, useRef, useState } from "react";
import type { ChapterVersion } from "../../types";

type ViewMode = "side-by-side" | "unified" | "raw";

type Op = { type: "same" | "added" | "removed"; text: string };

function splitParas(text: string): string[] {
  return text
    .split(/\r?\n\s*\r?\n/)
    .map((p) => p.trim())
    .filter((p) => p.length > 0);
}

function diffParas(left: string, right: string): Op[] {
  const a = splitParas(left);
  const b = splitParas(right);
  const m = a.length;
  const n = b.length;
  if (m === 0 && n === 0) return [];
  // LCS dp table
  const dp: Int32Array[] = Array.from({ length: m + 1 }, () => new Int32Array(n + 1));
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (a[i - 1] === b[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
      } else {
        dp[i][j] = dp[i - 1][j] >= dp[i][j - 1] ? dp[i - 1][j] : dp[i][j - 1];
      }
    }
  }
  const ops: Op[] = [];
  let i = m;
  let j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && a[i - 1] === b[j - 1]) {
      ops.push({ type: "same", text: a[i - 1] });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      ops.push({ type: "added", text: b[j - 1] });
      j--;
    } else {
      ops.push({ type: "removed", text: a[i - 1] });
      i--;
    }
  }
  ops.reverse();
  return ops;
}

function charCount(text: string): number {
  // CJK-aware: count CJK chars as 1, ascii word groups as 1 each.
  // 简单做法: 直接按 codePoint 数, 与后端 chapter.words.length 一致
  return text.length;
}

function pickDefaultVersions(versions: ChapterVersion[]) {
  // 左 = 最新 draft(或最旧), 右 = 最新 final
  const sorted = [...versions].sort((x, y) => x.id - y.id);
  const finalV = [...versions].reverse().find((v) => v.version_kind === "final");
  const draftV = [...versions].reverse().find((v) => v.version_kind === "draft");
  const rewriteV = [...versions].reverse().find((v) => v.version_kind === "rewrite");
  const left = draftV ?? rewriteV ?? sorted[0] ?? null;
  const right = finalV ?? rewriteV ?? sorted[sorted.length - 1] ?? null;
  return { left, right };
}

export function ChapterCompare({ versions }: { versions: ChapterVersion[] }) {
  const defaults = useMemo(() => pickDefaultVersions(versions), [versions]);
  const [leftId, setLeftId] = useState<number | null>(defaults.left?.id ?? null);
  const [rightId, setRightId] = useState<number | null>(defaults.right?.id ?? null);
  const [mode, setMode] = useState<ViewMode>("side-by-side");

  const left = versions.find((v) => v.id === leftId) ?? null;
  const right = versions.find((v) => v.id === rightId) ?? null;

  if (versions.length === 0) {
    return (
      <div className="card">
        <div className="muted">本章还没有任何版本。跑一次流水线后再来对比。</div>
      </div>
    );
  }

  return (
    <div className="compare-root">
      <div className="compare-toolbar">
        <div className="compare-picker">
          <label>左</label>
          <select value={leftId ?? ""} onChange={(e) => setLeftId(Number(e.target.value))}>
            {versions.map((v) => (
              <option key={v.id} value={v.id}>
                {v.version_kind} v{v.version_no} · {new Date(v.created_at).toLocaleTimeString("zh-CN")} · {v.content.length}字
              </option>
            ))}
          </select>
        </div>
        <div className="compare-picker">
          <label>右</label>
          <select value={rightId ?? ""} onChange={(e) => setRightId(Number(e.target.value))}>
            {versions.map((v) => (
              <option key={v.id} value={v.id}>
                {v.version_kind} v{v.version_no} · {new Date(v.created_at).toLocaleTimeString("zh-CN")} · {v.content.length}字
              </option>
            ))}
          </select>
        </div>
        <div className="compare-mode">
          {(["side-by-side", "unified", "raw"] as ViewMode[]).map((m) => (
            <button
              key={m}
              className={mode === m ? "active" : ""}
              onClick={() => setMode(m)}
              title={m}
            >
              {m === "side-by-side" ? "左右对比" : m === "unified" ? "统一差异" : "纯对比"}
            </button>
          ))}
        </div>
        <div className="spacer" />
        {left && right && <CompareStats left={left} right={right} />}
      </div>

      {!left || !right ? (
        <div className="card"><div className="muted">请选择左右两个版本。</div></div>
      ) : left.id === right.id ? (
        <div className="card"><div className="muted">左右选了同一个版本 —— 改一下选另一个版本吧。</div></div>
      ) : mode === "side-by-side" ? (
        <SideBySideView left={left} right={right} />
      ) : mode === "unified" ? (
        <UnifiedView left={left} right={right} />
      ) : (
        <RawView left={left} right={right} />
      )}
    </div>
  );
}

function CompareStats({ left, right }: { left: ChapterVersion; right: ChapterVersion }) {
  const ops = useMemo(() => diffParas(left.content, right.content), [left, right]);
  let added = 0;
  let removed = 0;
  for (const op of ops) {
    if (op.type === "added") added += charCount(op.text);
    else if (op.type === "removed") removed += charCount(op.text);
  }
  const lChars = left.content.length;
  const rChars = right.content.length;
  const delta = rChars - lChars;
  return (
    <div className="compare-stats">
      <span className="muted small">段:</span>
      <span className="mono">{splitParas(left.content).length}</span>
      <span className="muted small">→</span>
      <span className="mono">{splitParas(right.content).length}</span>
      <span className="sep" />
      <span className="muted small">字:</span>
      <span className="mono">{lChars.toLocaleString()}</span>
      <span className="muted small">→</span>
      <span className="mono">{rChars.toLocaleString()}</span>
      <span className="mono" style={{ color: delta >= 0 ? "var(--accent-good, #4ade80)" : "var(--accent-bad, #f87171)" }}>
        ({delta >= 0 ? "+" : ""}{delta})
      </span>
      <span className="sep" />
      <span className="compare-stat-pill add">+{added}</span>
      <span className="compare-stat-pill del">-{removed}</span>
    </div>
  );
}

function SideBySideView({ left, right }: { left: ChapterVersion; right: ChapterVersion }) {
  const ops = useMemo(() => diffParas(left.content, right.content), [left, right]);

  // 把 ops 切成 "行对": 每个 same/removed 算一行(右空),
  // 每个 same/added 算一行(左空)。same 出现时左右同一行。
  // 简化: 我们用 zip 方式 ——
  //   把 ops 摊平成两个数组, 长度 = max(left, right) 段的行数
  // 实际更好做法: 直接为每个 op 生成一对 (leftRow, rightRow):
  //   same   → (same, same)
  //   removed → (removed, null)
  //   added   → (null, added)
  const rows: Array<{ left: Op | null; right: Op | null }> = [];
  for (const op of ops) {
    if (op.type === "same") {
      rows.push({ left: op, right: op });
    } else if (op.type === "removed") {
      rows.push({ left: op, right: null });
    } else {
      rows.push({ left: null, right: op });
    }
  }

  // 同步滚动
  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const syncing = useRef(false);
  const bindScroll = (src: "left" | "right") => (e: React.UIEvent<HTMLDivElement>) => {
    if (syncing.current) return;
    syncing.current = true;
    const tgt = src === "left" ? rightRef.current : leftRef.current;
    if (tgt) tgt.scrollTop = e.currentTarget.scrollTop;
    requestAnimationFrame(() => {
      syncing.current = false;
    });
  };

  return (
    <div className="compare-sbs">
      <div className="compare-pane-header">
        <span className="compare-pane-title">
          {left.version_kind} v{left.version_no} · {new Date(left.created_at).toLocaleTimeString("zh-CN")} · {left.content.length}字
        </span>
        {left.score != null && <span className={`score-pill ${scoreClass(left.score)}`}>{left.score}</span>}
      </div>
      <div className="compare-pane-header">
        <span className="compare-pane-title">
          {right.version_kind} v{right.version_no} · {new Date(right.created_at).toLocaleTimeString("zh-CN")} · {right.content.length}字
        </span>
        {right.score != null && <span className={`score-pill ${scoreClass(right.score)}`}>{right.score}</span>}
      </div>

      <div className="compare-panes">
        <div className="compare-pane" ref={leftRef} onScroll={bindScroll("left")}>
          {rows.map((r, i) => (
            <DiffRow key={`L${i}`} side="left" op={r.left} />
          ))}
        </div>
        <div className="compare-divider" />
        <div className="compare-pane" ref={rightRef} onScroll={bindScroll("right")}>
          {rows.map((r, i) => (
            <DiffRow key={`R${i}`} side="right" op={r.right} />
          ))}
        </div>
      </div>
    </div>
  );
}

function DiffRow({ side, op }: { side: "left" | "right"; op: Op | null }) {
  if (!op) {
    return <div className="compare-row empty">&nbsp;</div>;
  }
  const cls =
    op.type === "same"
      ? "compare-row same"
      : op.type === "removed"
        ? `compare-row ${side === "left" ? "del" : "empty"}`
        : `compare-row ${side === "right" ? "add" : "empty"}`;
  return (
    <div className={cls}>
      {op.type === "same" && <span className="compare-marker same">·</span>}
      {op.type === "removed" && side === "left" && <span className="compare-marker del">−</span>}
      {op.type === "added" && side === "right" && <span className="compare-marker add">+</span>}
      <span className="compare-text">{op.text}</span>
    </div>
  );
}

function UnifiedView({ left, right }: { left: ChapterVersion; right: ChapterVersion }) {
  const ops = useMemo(() => diffParas(left.content, right.content), [left, right]);
  return (
    <div className="compare-unified">
      {ops.map((op, i) => {
        if (op.type === "same") {
          return <div key={i} className="unified-row same"><span className="unified-marker"> </span><span>{op.text}</span></div>;
        }
        if (op.type === "removed") {
          return <div key={i} className="unified-row del"><span className="unified-marker">−</span><span>{op.text}</span></div>;
        }
        return <div key={i} className="unified-row add"><span className="unified-marker">+</span><span>{op.text}</span></div>;
      })}
    </div>
  );
}

function RawView({ left, right }: { left: ChapterVersion; right: ChapterVersion }) {
  return (
    <div className="compare-raw">
      <div className="compare-pane-header">
        <span className="compare-pane-title">{left.version_kind} v{left.version_no}</span>
      </div>
      <div className="compare-pane-header">
        <span className="compare-pane-title">{right.version_kind} v{right.version_no}</span>
      </div>
      <div className="compare-panes">
        <div className="compare-pane">
          <pre className="compare-raw-text">{left.content}</pre>
        </div>
        <div className="compare-divider" />
        <div className="compare-pane">
          <pre className="compare-raw-text">{right.content}</pre>
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
