/**
 * PromptVersionViewer — 查看单个 Prompt 版本的正文,可选"对比当前激活版本" (Round 10)
 *
 * 用法:
 *   <PromptVersionViewer
 *      version={v}                    // 用户点中的那个版本
 *      activeVersion={a}              // 当前激活的版本 (用于 diff)
 *      onClose={() => ...}            // 关闭按钮
 *   />
 *
 * 两种显示模式:
 *   - "view":   单栏显示 body,带元信息 (状态/说明/统计/创建时间)
 *   - "diff":   side-by-side line diff (该版本 vs 激活版本)
 *
 * 算法: 行级 LCS,跟 ChapterCompare 同源但更轻 — prompt 正文是结构化
 * 文本(标题/列表/占位符),行级 diff 足够,不需要 char-level。
 */
import { useMemo, useState } from "react";
import type { PromptVersion } from "../../types";
import "./PromptVersionViewer.css";

type Mode = "view" | "diff";

type Op = { type: "same" | "added" | "removed"; text: string };

function diffLines(left: string, right: string): Op[] {
  const a = left.split(/\r?\n/);
  const b = right.split(/\r?\n/);
  const m = a.length;
  const n = b.length;
  if (m === 0 && n === 0) return [];
  const dp: Int32Array[] = Array.from({ length: m + 1 }, () => new Int32Array(n + 1));
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (a[i - 1] === b[j - 1]) dp[i][j] = dp[i - 1][j - 1] + 1;
      else dp[i][j] = dp[i - 1][j] >= dp[i][j - 1] ? dp[i - 1][j] : dp[i][j - 1];
    }
  }
  const ops: Op[] = [];
  let i = m;
  let j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && a[i - 1] === b[j - 1]) {
      ops.push({ type: "same", text: a[i - 1] });
      i--; j--;
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

function summarizeOps(ops: Op[]) {
  let added = 0, removed = 0, same = 0;
  for (const o of ops) {
    if (o.type === "added") added++;
    else if (o.type === "removed") removed++;
    else same++;
  }
  return { added, removed, same, total: ops.length };
}

export function PromptVersionViewer({
  version,
  activeVersion,
  onClose,
}: {
  version: PromptVersion;
  activeVersion: PromptVersion | null;
  onClose: () => void;
}) {
  const [mode, setMode] = useState<Mode>("view");
  const [copyState, setCopyState] = useState<"idle" | "ok" | "err">("idle");

  // The version we're viewing IS the active one — diff is meaningless.
  const showDiff = mode === "diff" && activeVersion && activeVersion.id !== version.id;

  const ops = useMemo(() => {
    if (!showDiff || !activeVersion) return [];
    return diffLines(activeVersion.body, version.body);
  }, [showDiff, activeVersion, version.body]);

  const summary = useMemo(() => summarizeOps(ops), [ops]);

  async function copyBody() {
    try {
      await navigator.clipboard.writeText(version.body);
      setCopyState("ok");
      setTimeout(() => setCopyState("idle"), 1500);
    } catch {
      setCopyState("err");
      setTimeout(() => setCopyState("idle"), 1500);
    }
  }

  return (
    <div className="pvv-root">
      <div className="pvv-head">
        <div>
          <div className="pvv-title">
            <span className="mono">v{version.version}</span>
            <span className={`pill ${version.status === "active" ? "succeeded" : version.status === "candidate" ? "pending" : "stopped"}`}>
              {version.status}
            </span>
            {activeVersion?.id === version.id && <span className="pvv-cur">当前激活</span>}
          </div>
          <div className="pvv-meta">
            <span>通过率 {(version.test_pass_rate * 100).toFixed(1)}%</span>
            <span>·</span>
            <span>调用 {version.usage_count} 次</span>
            <span>·</span>
            <span>{version.body.length} 字符 / {version.body.split(/\r?\n/).length} 行</span>
            <span>·</span>
            <span>{new Date(version.created_at).toLocaleString("zh-CN")}</span>
          </div>
          {version.change_note && <div className="pvv-note">📝 {version.change_note}</div>}
        </div>
        <div className="pvv-head-actions">
          {activeVersion && activeVersion.id !== version.id && (
            <div className="pvv-mode-toggle">
              <button className={mode === "view" ? "on" : ""} onClick={() => setMode("view")}>查看</button>
              <button className={mode === "diff" ? "on" : ""} onClick={() => setMode("diff")}>对比 v{activeVersion.version}</button>
            </div>
          )}
          <button className="pvv-copy" onClick={copyBody}>
            {copyState === "ok" ? "已复制" : copyState === "err" ? "复制失败" : "复制正文"}
          </button>
          <button className="pvv-close" onClick={onClose} aria-label="关闭">×</button>
        </div>
      </div>

      {mode === "view" || !showDiff ? (
        <pre className="pvv-body">{version.body}</pre>
      ) : (
        <div className="pvv-diff">
          <div className="pvv-diff-summary">
            <span className="added">+{summary.added} 行</span>
            <span className="removed">−{summary.removed} 行</span>
            <span className="same">·{summary.same} 行未变</span>
            <span className="muted">对比基准: v{activeVersion!.version} → v{version.version}</span>
          </div>
          <pre className="pvv-body pvv-diff-body">
            {ops.map((o, idx) => (
              <div key={idx} className={`pvv-line pvv-line-${o.type}`}>
                <span className="pvv-line-marker">
                  {o.type === "added" ? "+" : o.type === "removed" ? "−" : " "}
                </span>
                <span className="pvv-line-text">{o.text || " "}</span>
              </div>
            ))}
          </pre>
        </div>
      )}
    </div>
  );
}
