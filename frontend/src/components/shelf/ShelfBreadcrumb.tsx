/**
 * ShelfBreadcrumb — 通用面包屑 + 返回按钮
 *
 * P0 阶段 (01 §2.2 / §3 / §4.4) 要求: 所有二级页面顶部必须有
 *   1. 「← 返回{一级书架名}」按钮 — 显式 navigate 到一级路径
 *   2. 「一级书架 / 当前对象 / 当前 tab」面包屑
 *
 * 不要依赖 window.history.back() (P0 §8 禁止事项 1). 直接 import
 * Link 跟 useNavigate, 用 to= 跳转. 这条规则在 R 阶段很多次都踩过
 * 坑 (用户刷二级页 history 里只有 1 条, 返回失效), 现在统一规范.
 *
 * Props:
 *   - items: 面包屑条目, 第一项是「一级书架」(可点击, 跳一级),
 *           最后一项是当前 tab (无 onClick/to, 仅文字)
 *   - backTo / backLabel: 顶部「← 返回XXX」按钮, 不在面包屑里 ——
 *           显眼的固定按钮, 即便用户错过了面包屑也能点回
 *
 * 用法 (ProjectPage 顶部):
 *   <ShelfBreadcrumb
 *     backTo="/projects"
 *     backLabel="返回项目书架"
 *     items={[
 *       { label: "项目书架", to: "/projects" },
 *       { label: project.name },
 *       { label: TAB_LABELS[tab] },
 *     ]}
 *   />
 */
import { Link } from "react-router-dom";

export type ShelfBreadcrumbItem = {
  label: string;
  to?: string;
  onClick?: () => void;
};

export type ShelfBreadcrumbProps = {
  /** 「← 返回XX」按钮跳的目标路由, 必填 (P0 §2.1 强制) */
  backTo: string;
  /** 按钮文字, 例如 "返回项目书架" / "返回拆书书架" / "返回记忆书架" */
  backLabel: string;
  /** 面包屑条目, 第一项必须是一级书架 (P0 §4.4 要求 2) */
  items: ShelfBreadcrumbItem[];
  /** 可选 className, 留给页面自定 padding */
  className?: string;
};

export function ShelfBreadcrumb({
  backTo,
  backLabel,
  items,
  className,
}: ShelfBreadcrumbProps) {
  return (
    <div className={`shelf-breadcrumb ${className ?? ""}`.trim()}>
      <Link
        to={backTo}
        className="shelf-back-button"
        aria-label={backLabel}
        // 显式 preventDefault + 路由跳转, 避免依赖浏览器 history
        // 跟未来如果挂 in-app router state 的兼容 (P0 §8 禁 1)
        onClick={(e) => {
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
          e.preventDefault();
          window.location.assign(backTo);
        }}
      >
        <span className="shelf-back-arrow" aria-hidden>←</span>
        <span>{backLabel}</span>
      </Link>

      {items.length > 0 && (
        <nav className="shelf-breadcrumb-list" aria-label="breadcrumb">
          {items.map((it, i) => {
            const isLast = i === items.length - 1;
            const content = it.to ? (
              <Link
                to={it.to}
                className="shelf-breadcrumb-link"
                onClick={(e) => {
                  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
                  if (it.onClick) {
                    e.preventDefault();
                    it.onClick();
                  }
                }}
              >
                {it.label}
              </Link>
            ) : (
              <span className="shelf-breadcrumb-text">{it.label}</span>
            );
            return (
              <span key={`${i}-${it.label}`} className="shelf-breadcrumb-item">
                {i > 0 && <span className="shelf-breadcrumb-sep" aria-hidden> / </span>}
                {content}
              </span>
            );
          })}
        </nav>
      )}
    </div>
  );
}
