/**
 * ShelfRow — 书架中的一层横架
 *
 * P0 §4.2: 一排书. 水平 flex 排列, 超过容器宽度自然 wrap 到下一排.
 * 标题在左 (固定宽度, 类似图书馆的"分类标签"), 书在右. 整条
 * ShelfRow 之间有木板 (shelf-row-wood 渐变) 视觉, 但实现是简洁
 * 的横向 flex + 行间 gap + border-bottom, 不真的渲染木板图.
 *
 * 用法 (P1 项目书架):
 *   <ShelfRow title="进行中 (4)">
 *     {projects.filter(p => p.status === "active").map(p =>
 *       <ShelfBook key={p.id} ... onClick={() => navigate(`/projects/${p.id}`)} />
 *     )}
 *   </ShelfRow>
 *   <ShelfRow title="已完成 (2)">
 *     {projects.filter(p => p.status === "done").map(p => <ShelfBook ... />)}
 *   </ShelfRow>
 */
import type { ReactNode } from "react";

export type ShelfRowProps = {
  title?: string;
  subtitle?: string;
  children: ReactNode;
  /** 强制空状态 — 当 children 为空数组时显示 */
  emptyHint?: ReactNode;
};

export function ShelfRow({ title, subtitle, children, emptyHint }: ShelfRowProps) {
  const childArray = Array.isArray(children) ? children : [children];
  const isEmpty = childArray.length === 0;
  return (
    <section className="shelf-row">
      {(title || subtitle) && (
        <header className="shelf-row-head">
          {title && <h3 className="shelf-row-title">{title}</h3>}
          {subtitle && <span className="shelf-row-subtitle">{subtitle}</span>}
        </header>
      )}
      <div className="shelf-row-board">
        {isEmpty ? (
          <div className="shelf-row-empty">{emptyHint ?? "— 空架 —"}</div>
        ) : (
          <div className="shelf-row-books">{children}</div>
        )}
      </div>
    </section>
  );
}
