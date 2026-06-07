/**
 * CreateProjectDialog — 新建项目弹窗 (P0 修复)
 *
 * 原 ProjectsPage 有 `creating` state 但没渲染表单, 用户点了按钮
 * 看不到任何东西。 这个组件把表单全收进来, ProjectsPage 只传
 * open / busy / error / onClose / onSubmit, 不再持有 form 字段。
 */
import { useEffect, useState } from "react";

export type CreateProjectPayload = {
  name: string;
  genre: string;
  category?: string | null;
  target_word_count: number;
  target_chapter_count: number;
  description?: string | null;
  pinned?: boolean;
};

const GENRES = [
  "玄幻", "都市", "历史", "科幻", "悬疑", "言情", "武侠", "仙侠", "奇幻", "军事", "游戏", "体育", "其他",
];

const DEFAULTS = {
  name: "",
  genre: "玄幻",
  targetWords: 3_000_000,
  targetChapters: 2000,
  description: "",
  pinned: false,
  openAfterCreate: true,
};

export function CreateProjectDialog(props: {
  open: boolean;
  busy?: boolean;
  error?: string | null;
  onClose: () => void;
  onSubmit: (payload: CreateProjectPayload, options: { openAfterCreate: boolean }) => Promise<void> | void;
}) {
  const { open, busy, error, onClose, onSubmit } = props;

  const [name, setName] = useState(DEFAULTS.name);
  const [genre, setGenre] = useState(DEFAULTS.genre);
  const [targetWords, setTargetWords] = useState(DEFAULTS.targetWords);
  const [targetChapters, setTargetChapters] = useState(DEFAULTS.targetChapters);
  const [description, setDescription] = useState(DEFAULTS.description);
  const [pinned, setPinned] = useState(DEFAULTS.pinned);
  const [openAfterCreate, setOpenAfterCreate] = useState(DEFAULTS.openAfterCreate);
  const [localError, setLocalError] = useState<string | null>(null);

  // open 从 false → true 时重置
  useEffect(() => {
    if (open) {
      setName(DEFAULTS.name);
      setGenre(DEFAULTS.genre);
      setTargetWords(DEFAULTS.targetWords);
      setTargetChapters(DEFAULTS.targetChapters);
      setDescription(DEFAULTS.description);
      setPinned(DEFAULTS.pinned);
      setOpenAfterCreate(DEFAULTS.openAfterCreate);
      setLocalError(null);
    }
  }, [open]);

  // Esc 关闭 (busy 时不让关)
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onClose]);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    const trimmed = name.trim();
    if (!trimmed) {
      setLocalError("书名不能为空。");
      return;
    }
    if (trimmed.length > 200) {
      setLocalError("书名不能超过 200 字。");
      return;
    }
    if (!Number.isFinite(targetWords)) {
      setLocalError("目标字数必须是数字。");
      return;
    }
    if (!Number.isFinite(targetChapters)) {
      setLocalError("目标章节必须是数字。");
      return;
    }
    await onSubmit(
      {
        name: trimmed,
        genre,
        category: null, // 后端默认用 genre
        target_word_count: targetWords,
        target_chapter_count: targetChapters,
        description: description.trim() || null,
        pinned,
      },
      { openAfterCreate },
    );
  };

  const mergedError = localError ?? error ?? null;

  return (
    <div
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.45)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 1000,
      }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          width: 480, maxWidth: "calc(100vw - 32px)",
          background: "var(--bg-card, #1e1e1e)",
          color: "var(--text-primary, #eee)",
          border: "1px solid var(--border-color, #333)",
          borderRadius: 8,
          padding: 20,
          display: "flex", flexDirection: "column", gap: 14,
          boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0, fontSize: 16 }}>新建项目</h3>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: busy ? "not-allowed" : "pointer", fontSize: 18 }}
            aria-label="关闭"
          >
            ×
          </button>
        </div>

        {/* 书名 */}
        <Field label="书名" required>
          <input
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="给你的新书写个名字"
            maxLength={200}
            autoFocus
            disabled={busy}
          />
        </Field>

        {/* 类型 + 目标字数 + 目标章节 */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
          <Field label="类型" required>
            <select
              className="input"
              value={genre}
              onChange={(e) => setGenre(e.target.value)}
              disabled={busy}
            >
              {GENRES.map((g) => <option key={g} value={g}>{g}</option>)}
            </select>
          </Field>
          <Field label="目标字数">
            <input
              className="input"
              type="number"
              step={100_000}
              value={targetWords}
              onChange={(e) => setTargetWords(Number(e.target.value) || 0)}
              disabled={busy}
            />
          </Field>
          <Field label="目标章节">
            <input
              className="input"
              type="number"
              step={10}
              value={targetChapters}
              onChange={(e) => setTargetChapters(Number(e.target.value) || 0)}
              disabled={busy}
            />
          </Field>
        </div>

        {/* 简介 */}
        <Field label="简介">
          <textarea
            className="input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="一句话介绍这本书 (可空)"
            rows={3}
            maxLength={2000}
            disabled={busy}
          />
        </Field>

        {/* 选项 */}
        <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
          <input
            type="checkbox"
            checked={pinned}
            onChange={(e) => setPinned(e.target.checked)}
            disabled={busy}
          />
          置顶
        </label>
        <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
          <input
            type="checkbox"
            checked={openAfterCreate}
            onChange={(e) => setOpenAfterCreate(e.target.checked)}
            disabled={busy}
          />
          创建后打开工作台
        </label>

        {/* 错误条 */}
        {mergedError && (
          <div
            role="alert"
            style={{
              padding: "8px 12px",
              background: "var(--danger-bg, #fdd)",
              color: "var(--danger-text, #900)",
              border: "1px solid var(--danger-border, #c66)",
              borderRadius: 4,
              fontSize: 12,
              whiteSpace: "pre-wrap",
            }}
          >
            ⚠ {mergedError}
          </div>
        )}

        {/* 按钮 */}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 4 }}>
          <button type="button" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button type="submit" className="primary" disabled={busy}>
            {busy ? "创建中…" : "创建"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12 }}>
      <span style={{ color: "var(--text-muted)" }}>
        {label}{required && <span style={{ color: "var(--accent-red, #c45858)" }}> *</span>}
      </span>
      {children}
    </label>
  );
}
