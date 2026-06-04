/**
 * ShelfSidePanel — 窄侧边摘要卡
 *
 * P0 §4.6: 显示选中对象的"摘要元数据" (章节数 / 字数 / 状态 /
 * 进度条). 用在 ShelfLayout.left 槽里 (因为不是太长的详情, 只
 * 一栏就够; 长详情走 ShelfDetailPanel). 跟 ShelfDetailPanel 共享
 * 颜色 token.
 */
import type { ReactNode } from "react";

export type ShelfSidePanelProps = {
  title?: string;
  /** 顶部状态色条 (6 选 1 颜色 token) */
  accentColor?: "blue" | "gold" | "purple" | "green" | "red" | "gray";
  children: ReactNode;
};

export function ShelfSidePanel({
  title,
  accentColor = "blue",
  children,
}: ShelfSidePanelProps) {
  return (
    <div
      className="shelf-side-panel"
      style={{ ["--shelf-accent" as any]: `var(--shelf-color-${accentColor}, #3a6ea5)` }}
    >
      {title && <h4 className="shelf-side-panel-title">{title}</h4>}
      <div className="shelf-side-panel-body">{children}</div>
    </div>
  );
}
