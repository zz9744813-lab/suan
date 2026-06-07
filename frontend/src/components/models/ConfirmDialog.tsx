/**
 * ConfirmDialog — 通用确认弹窗 (P-Delete-Preview)
 *
 * 一个项目风格的二次确认弹窗, 替代浏览器原生 `confirm()`。
 * 与 ``FirstRunGuide`` / ``AgentRoleEditorModal`` 等保持一致的
 * ``.modal-backdrop`` / ``.modal`` 样式, 同时提供 danger 风格
 * 的标题栏和确认按钮。
 *
 * 用法:
 *   <ConfirmDialog
 *     open={open}
 *     title="删除 Provider?"
 *     dangerLevel="danger"
 *     summary="将删除 Provider「stub」, 并级联删除 3 个角色绑定..."
 *     confirmLabel="确认删除"
 *     confirmDisabled={busy}
 *     onCancel={() => setOpen(false)}
 *     onConfirm={async () => { await deleteProvider(id); setOpen(false); }}
 *   />
 *
 * 异步 onConfirm: 内部捕获异常, 抛给调用方; 调用方可在 catch
 * 里把错误塞进页面级的 ``errorMsg`` 状态。按钮在 pending 期间
 * 禁用, 防止重复点击。
 */
import { useState } from "react";

export type ConfirmDialogDangerLevel = "safe" | "caution" | "danger";

export type ConfirmDialogProps = {
  open: boolean;
  title: string;
  /**
   * Optional one-line subtitle shown under the title (e.g. the
   * provider name + base_url). Pass ``null`` to hide.
   */
  subtitle?: React.ReactNode | null;
  /**
   * Body text. Keep it short — the dialog body is meant to be a
   * one-paragraph summary, not a wall of text. Longer details
   * (binding list, call event count) should go in ``details``.
   */
  summary: React.ReactNode;
  /**
   * Optional structured details. The delete-preview dialog uses
   * this for the "will cascade these role bindings" list. We
   * accept any React node so callers can shape the layout
   * (list, table, custom badge, ...).
   */
  details?: React.ReactNode;
  /**
   * Drives the header colour and confirm button style. Defaults
   * to ``danger`` so misuse is hard — callers have to opt in to
   * the calmer styles for safe / cautionary flows.
   */
  dangerLevel?: ConfirmDialogDangerLevel;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmDisabled?: boolean;
  onCancel: () => void;
  onConfirm: () => Promise<void> | void;
};

const DANGER_HEAD: Record<ConfirmDialogDangerLevel, { color: string; emoji: string; buttonClass: string }> = {
  safe:    { color: "var(--accent, #5d9c5d)", emoji: "🗑️", buttonClass: "" },
  caution: { color: "#e3b75f", emoji: "⚠️", buttonClass: "warn" },
  danger:  { color: "#c45858", emoji: "🚨", buttonClass: "danger" },
};

export function ConfirmDialog({
  open,
  title,
  subtitle,
  summary,
  details,
  dangerLevel = "danger",
  confirmLabel = "确认",
  cancelLabel = "取消",
  confirmDisabled = false,
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  const [busy, setBusy] = useState(false);
  const [localErr, setLocalErr] = useState<string | null>(null);

  if (!open) return null;
  const head = DANGER_HEAD[dangerLevel];

  const handleConfirm = async () => {
    if (busy || confirmDisabled) return;
    setBusy(true);
    setLocalErr(null);
    try {
      await onConfirm();
      // Caller is responsible for closing the dialog (via setting
      // its own ``open`` to false on success). We only reset
      // ``busy`` here so the loading state clears.
    } catch (e: any) {
      setLocalErr(String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="modal-backdrop"
      onClick={() => {
        if (busy) return;
        onCancel();
      }}
    >
      <div
        className="modal confirm-dialog-modal"
        onClick={(e) => e.stopPropagation()}
        style={{ width: 480 }}
        data-danger={dangerLevel}
      >
        <div
          className="modal-head"
          style={{
            borderBottom: `2px solid ${head.color}`,
            color: head.color,
          }}
        >
          <h3 className="serif" style={{ color: head.color }}>
            <span style={{ marginRight: 6 }}>{head.emoji}</span>
            {title}
          </h3>
          <button
            onClick={onCancel}
            className="modal-close"
            disabled={busy}
            title="关闭"
          >
            ✕
          </button>
        </div>

        <div className="modal-body">
          {subtitle != null && (
            <div
              className="muted small"
              style={{ marginBottom: 10, fontFamily: "monospace", wordBreak: "break-all" }}
            >
              {subtitle}
            </div>
          )}

          <div
            style={{
              fontSize: 13,
              lineHeight: 1.7,
              color: "var(--text-primary)",
              whiteSpace: "pre-wrap",
              marginBottom: details ? 12 : 0,
            }}
          >
            {summary}
          </div>

          {details && (
            <div
              style={{
                background: "var(--bg-tertiary, rgba(255,255,255,0.04))",
                border: "1px solid var(--border-secondary, #2c333b)",
                borderRadius: 4,
                padding: "8px 10px",
                fontSize: 12,
                marginBottom: 4,
              }}
            >
              {details}
            </div>
          )}

          {localErr && (
            <div
              className="error"
              style={{
                marginTop: 10,
                padding: "6px 8px",
                background: "rgba(196,88,88,0.10)",
                border: "1px solid #c45858",
                borderRadius: 4,
                fontSize: 12,
                whiteSpace: "pre-wrap",
              }}
            >
              {localErr}
            </div>
          )}
        </div>

        <div
          className="modal-foot"
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
            padding: "10px 16px",
            borderTop: "1px solid var(--border, #2c333b)",
          }}
        >
          <button onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </button>
          <button
            className={head.buttonClass}
            onClick={handleConfirm}
            disabled={busy || confirmDisabled}
            style={
              head.buttonClass
                ? undefined
                : { background: head.color, color: "#fff", borderColor: head.color }
            }
          >
            {busy ? "处理中..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
