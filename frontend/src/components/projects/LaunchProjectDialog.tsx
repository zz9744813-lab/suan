/**
 * LaunchProjectDialog — 双模式创作启动弹窗
 *
 * 模式一 (半自动): 用户提供大纲/人物/设定文本 → 系统自动创建并启动写作
 * 模式二 (全自动): 系统全自动 → LLM 生成一切 → 启动写作
 */
import { useState } from "react";
import { launchProject, type LaunchMode } from "../../api";

type Mode = "semi_auto" | "full_auto";

const OUTLINE_HELP = `支持多种格式：
• 管道符: 1|开局被逐|主角因废脉被除名|80
• 编号行: 1. 开局被逐
• 纯标题: 每行一章标题（自动编号）
• JSON: [{"chapter_no":1,"title":"...","summary":"..."}]`;

const CHAR_HELP = `支持多种格式：
• 管道符: 叶凡|protagonist|天赋异禀的少年
• 纯名字: 每行一个人物名
• JSON: [{"name":"...","role":"protagonist","profile":{}}]`;

export function LaunchProjectDialog(props: {
  open: boolean;
  projectId: number;
  projectName: string;
  onClose: () => void;
  onLaunched: () => void;
}) {
  const { open, projectId, projectName, onClose, onLaunched } = props;
  const [mode, setMode] = useState<Mode>("semi_auto");
  const [outlineText, setOutlineText] = useState("");
  const [characterText, setCharacterText] = useState("");
  const [bibleText, setBibleText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const handleLaunch = async () => {
    setBusy(true);
    setError(null);
    try {
      if (mode === "semi_auto") {
        if (!outlineText.trim() && !characterText.trim() && !bibleText.trim()) {
          setError("半自动模式需要至少提供一项素材（大纲/人物/设定）。");
          setBusy(false);
          return;
        }
        await launchProject(projectId, "semi_auto", {
          outline_text: outlineText.trim() || undefined,
          character_text: characterText.trim() || undefined,
          bible_text: bibleText.trim() || undefined,
        });
      } else {
        await launchProject(projectId, "full_auto");
      }
      onLaunched();
      onClose();
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.5)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 1000,
      }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <div
        style={{
          width: 640, maxWidth: "calc(100vw - 32px)",
          maxHeight: "calc(100vh - 64px)",
          overflow: "auto",
          background: "var(--bg-card, #1e1e1e)",
          color: "var(--text-primary, #eee)",
          border: "1px solid var(--border-color, #333)",
          borderRadius: 12,
          padding: 24,
          display: "flex", flexDirection: "column", gap: 16,
          boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
        }}
      >
        {/* 标题 */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0, fontSize: 18 }}>启动创作 — {projectName}</h3>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 20 }}
          >
            ×
          </button>
        </div>

        {/* 模式选择卡片 */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <ModeCard
            selected={mode === "semi_auto"}
            onClick={() => setMode("semi_auto")}
            icon="📋"
            title="半自动模式"
            desc="你提供大纲、人物、设定，系统自动执行写作"
          />
          <ModeCard
            selected={mode === "full_auto"}
            onClick={() => setMode("full_auto")}
            icon="🚀"
            title="全自动模式"
            desc="AI 自动生成一切，从大纲到正文全自动"
          />
        </div>

        {/* 模式一: 素材输入 */}
        {mode === "semi_auto" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <label style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4, fontSize: 13 }}>
                <span style={{ fontWeight: 600 }}>大纲</span>
                <span style={{ color: "var(--text-muted)", fontSize: 11 }}>{OUTLINE_HELP.split("\n")[0]}</span>
              </label>
              <textarea
                className="input"
                value={outlineText}
                onChange={(e) => setOutlineText(e.target.value)}
                placeholder={`1|开局被逐|主角因废脉被宗门除名|80\n2|残玉觉醒|主角跌入山谷偶得残玉|85`}
                rows={6}
                style={{ minHeight: 100, resize: "vertical" }}
                disabled={busy}
              />
            </div>
            <div>
              <label style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4, fontSize: 13 }}>
                <span style={{ fontWeight: 600 }}>人物设定</span>
                <span style={{ color: "var(--text-muted)", fontSize: 11 }}>{CHAR_HELP.split("\n")[0]}</span>
              </label>
              <textarea
                className="input"
                value={characterText}
                onChange={(e) => setCharacterText(e.target.value)}
                placeholder={`叶凡|protagonist|天赋异禀的少年\n苏橙|supporting|青梅竹马`}
                rows={4}
                style={{ minHeight: 80, resize: "vertical" }}
                disabled={busy}
              />
            </div>
            <div>
              <label style={{ display: "block", marginBottom: 4, fontSize: 13, fontWeight: 600 }}>
                世界观 / 设定
              </label>
              <textarea
                className="input"
                value={bibleText}
                onChange={(e) => setBibleText(e.target.value)}
                placeholder="描述这个世界的规则、力量体系、主要势力..."
                rows={4}
                style={{ minHeight: 80, resize: "vertical" }}
                disabled={busy}
              />
            </div>
          </div>
        )}

        {/* 模式二: 确认提示 */}
        {mode === "full_auto" && (
          <div style={{
            background: "var(--bg-elevated, #252525)",
            borderRadius: 8,
            padding: 16,
            fontSize: 14,
            lineHeight: 1.6,
          }}>
            <p style={{ margin: "0 0 8px" }}>
              <strong>全自动模式</strong>将自动完成以下步骤：
            </p>
            <ol style={{ margin: 0, paddingLeft: 20, color: "var(--text-secondary)" }}>
              <li>AI 生成前 30 章详细大纲</li>
              <li>AI 设计主要人物（最多 15 人）</li>
              <li>AI 撰写世界观设定</li>
              <li>自动从第一章开始写作管线</li>
              <li>完成后自动续写下一章（可在策略中关闭）</li>
            </ol>
            <p style={{ margin: "8px 0 0", color: "var(--text-muted)", fontSize: 12 }}>
              提示：全自动模式会消耗较多 Token，建议确保模型配置正确后再启动。
            </p>
          </div>
        )}

        {/* 错误 */}
        {error && (
          <div role="alert" style={{
            padding: "8px 12px",
            background: "rgba(238,77,90,0.1)",
            color: "var(--state-error, #ee4d5a)",
            border: "1px solid rgba(238,77,90,0.3)",
            borderRadius: 6,
            fontSize: 13,
          }}>
            {error}
          </div>
        )}

        {/* 按钮 */}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 4 }}>
          <button onClick={onClose} disabled={busy}>取消</button>
          <button
            className="primary"
            onClick={handleLaunch}
            disabled={busy}
            style={{
              background: mode === "full_auto"
                ? "linear-gradient(135deg, var(--accent-gold, #3f7cff), var(--accent-violet, #7b61ff))"
                : undefined,
            }}
          >
            {busy ? "启动中…" : mode === "semi_auto" ? "启动写作" : "🚀 全自动启动"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ModeCard({ selected, onClick, icon, title, desc }: {
  selected: boolean;
  onClick: () => void;
  icon: string;
  title: string;
  desc: string;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "flex", flexDirection: "column", gap: 6,
        padding: 16,
        background: selected
          ? "linear-gradient(135deg, rgba(63,124,255,0.15), rgba(123,97,255,0.1))"
          : "var(--bg-elevated, #252525)",
        border: selected
          ? "2px solid var(--accent-gold, #3f7cff)"
          : "1px solid var(--border-color, #333)",
        borderRadius: 10,
        cursor: "pointer",
        textAlign: "left",
        transition: "all 0.15s ease",
      }}
    >
      <span style={{ fontSize: 24 }}>{icon}</span>
      <span style={{ fontWeight: 600, fontSize: 14 }}>{title}</span>
      <span style={{ color: "var(--text-muted)", fontSize: 12, lineHeight: 1.4 }}>{desc}</span>
    </button>
  );
}
