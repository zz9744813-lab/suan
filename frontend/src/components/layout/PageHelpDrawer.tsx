/**
 * PageHelpDrawer — 右侧滑出的帮助抽屉
 *
 * 替代各页面里"长介绍文案"占据首屏空间的做法.
 * 描述类内容都进这里, 不挤压主业务区域.
 */
import { type ReactNode } from "react";
import "./PageTopbar.css";

export function PageHelpDrawer({
  title,
  children,
  onClose,
}: {
  title: string;
  children?: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="page-help-backdrop" onClick={onClose}>
      <aside
        className="page-help-drawer"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <header className="page-help-head">
          <h2>{title}</h2>
          <button onClick={onClose} title="关闭" aria-label="关闭">×</button>
        </header>
        <div className="page-help-body">
          {children ?? <p>暂无说明.</p>}
        </div>
      </aside>
    </div>
  );
}
