/**
 * ShelfToolbar — 书架上方工具条
 *
 * P0 §4.5: 搜索 + 类型过滤 + 新建按钮 + 排序. 用在 ShelfLayout.left
 * 槽里. 这条组件里只搭容器跟样式, 内容由调用方填 (因为不同书架
 * 的过滤维度不一样: 项目过滤按 genre, 拆书按 status, 记忆按 tag).
 *
 * 用法:
 *   <ShelfToolbar>
 *     <input className="input" placeholder="🔍 搜索项目" />
 *     <div className="shelf-toolbar-chips">
 *       {GENRES.map(g => <button className="shelf-toolbar-chip">...</button>)}
 *     </div>
 *     <button className="primary">+ 新建项目</button>
 *   </ShelfToolbar>
 */
import type { ReactNode } from "react";

export type ShelfToolbarProps = {
  children: ReactNode;
};

export function ShelfToolbar({ children }: ShelfToolbarProps) {
  return <div className="shelf-toolbar">{children}</div>;
}
