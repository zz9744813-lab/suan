/**
 * PageTopbar — 56px 紧凑顶部栏 (NF2 阶段 0)
 *
 * 替换各页面大块"返回 + 标题 + 说明"区域.
 * 规则:
 *   1. 不放长介绍文案 (进入帮助抽屉)
 *   2. 不放大标题 (17px / 800)
 *   3. actions 在右侧, context chips 居中
 *   4. 高度固定 56px
 */
import { useState, type ReactNode } from "react";
import { PageHelpDrawer } from "./PageHelpDrawer";
import "./PageTopbar.css";

export type PageTopbarAction = {
  label: string;
  icon?: string;
  variant?: "default" | "primary" | "danger" | "ghost";
  onClick?: () => void;
  disabled?: boolean;
  loading?: boolean;
  title?: string;
};

export type PageTopbarContextChip = {
  label: string;
  variant?: "default" | "info" | "success" | "warning" | "danger";
  title?: string;
};

export type PageTopbarProps = {
  title: string;
  icon?: string;
  subtitle?: string;
  context?: (string | PageTopbarContextChip)[];
  actions?: (PageTopbarAction | ReactNode)[];
  /** 帮助抽屉 (点 ? 按钮) */
  helpTitle?: string;
  helpContent?: ReactNode;
  /** 右侧额外内容 (例如状态点 / 用户菜单) */
  rightExtra?: ReactNode;
  /** 粘性定位 (默认 true) */
  sticky?: boolean;
};

function isAction(a: PageTopbarAction | ReactNode): a is PageTopbarAction {
  return (
    typeof a === "object" &&
    a !== null &&
    "label" in (a as object) &&
    "onClick" in (a as object)
  );
}

function Chip({ item }: { item: string | PageTopbarContextChip }) {
  if (typeof item === "string") {
    return <span className="page-topbar-chip">{item}</span>;
  }
  return (
    <span
      className={`page-topbar-chip chip-${item.variant ?? "default"}`}
      title={item.title ?? item.label}
    >
      {item.label}
    </span>
  );
}

export function PageTopbar({
  title,
  icon,
  subtitle,
  context,
  actions,
  helpTitle,
  helpContent,
  rightExtra,
}: PageTopbarProps) {
  const [helpOpen, setHelpOpen] = useState(false);

  return (
    <header className="page-topbar">
      <div className="page-topbar-left">
        {icon && <span className="page-topbar-icon">{icon}</span>}
        <div className="page-topbar-title-block">
          <h1 className="page-topbar-title">{title}</h1>
          {subtitle && <div className="page-topbar-subtitle">{subtitle}</div>}
        </div>
        {context && context.length > 0 && (
          <div className="page-topbar-context">
            {context.map((c, i) => (
              <Chip key={i} item={c} />
            ))}
          </div>
        )}
      </div>

      <div className="page-topbar-right">
        {actions && actions.length > 0 && (
          <div className="page-topbar-actions">
            {actions.map((a, i) => {
              if (!isAction(a)) return <span key={i}>{a}</span>;
              const cls = a.variant === "primary"
                ? "primary"
                : a.variant === "danger"
                  ? "danger"
                  : a.variant === "ghost"
                    ? "ghost"
                    : "";
              return (
                <button
                  key={i}
                  className={cls}
                  disabled={a.disabled || a.loading}
                  onClick={a.onClick}
                  title={a.title ?? a.label}
                >
                  {a.loading ? "处理中..." : a.icon ? `${a.icon} ${a.label}` : a.label}
                </button>
              );
            })}
          </div>
        )}
        {rightExtra}
        {(helpTitle || helpContent) && (
          <button
            className="page-topbar-help"
            onClick={() => setHelpOpen(true)}
            title="查看页面说明"
            aria-label="帮助"
          >
            ?
          </button>
        )}
      </div>

      {helpOpen && (
        <PageHelpDrawer
          title={helpTitle ?? title}
          onClose={() => setHelpOpen(false)}
        >
          {helpContent}
        </PageHelpDrawer>
      )}
    </header>
  );
}
