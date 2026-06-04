/**
 * ShelfLayout — 三栏书架布局
 *
 * P0 §4.1: 三栏 (左: 统计/筛选/说明, 中: 书架主体, 右: 选中摘要)
 * 用 CSS Grid: 240px / 1fr / 320px. 窗口窄 (<1100px) 时降级为单列,
 * 跟现有的 AppShell 4-zone 响应式一致 (P0 §6 路由规范 + R17
 * 加的 @media (max-width: 1100px)).
 *
 * 用法 (P1 项目书架):
 *   <ShelfLayout
 *     title="项目书架"
 *     subtitle="一本书 = 一个项目"
 *     left={<ShelfToolbar />}
 *     center={
 *       <>
 *         <ShelfRow title="进行中">...books...</ShelfRow>
 *         <ShelfRow title="已完成">...books...</ShelfRow>
 *       </>
 *     }
 *     right={<ShelfDetailPanel ... />}
 *   />
 */
import type { ReactNode } from "react";
import { ShelfBreadcrumb, type ShelfBreadcrumbItem } from "./ShelfBreadcrumb";

export type ShelfLayoutProps = {
  title: string;
  subtitle?: string;
  /** 顶部面包屑 items, 第一个是一级书架 */
  breadcrumb?: ShelfBreadcrumbItem[];
  /** 顶部返回按钮的目标 */
  backTo?: string;
  backLabel?: string;
  left: ReactNode;
  center: ReactNode;
  right: ReactNode;
};

export function ShelfLayout({
  title,
  subtitle,
  breadcrumb,
  backTo,
  backLabel,
  left,
  center,
  right,
}: ShelfLayoutProps) {
  return (
    <div className="shelf-layout">
      {(backTo || breadcrumb) && (
        <header className="shelf-layout-head">
          <ShelfBreadcrumb
            backTo={backTo ?? (breadcrumb?.[0]?.to ?? "/")}
            backLabel={backLabel ?? "返回"}
            items={breadcrumb ?? []}
          />
        </header>
      )}
      <div className="shelf-layout-title">
        <h1 className="shelf-layout-h1">{title}</h1>
        {subtitle && <p className="shelf-layout-sub">{subtitle}</p>}
      </div>
      <div className="shelf-layout-body">
        <aside className="shelf-layout-left">{left}</aside>
        <main className="shelf-layout-center">{center}</main>
        <aside className="shelf-layout-right">{right}</aside>
      </div>
    </div>
  );
}
