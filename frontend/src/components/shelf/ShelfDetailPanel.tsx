/**
 * ShelfDetailPanel — 大详情卡
 *
 * P0 §4.7: 选中对象的所有元数据 + 操作按钮. 用在 ShelfLayout.right
 * 槽里. 比 ShelfSidePanel 宽, 显示完整状态 / 进度 / Token / 耗时
 * / 最近日志, 跟"角色绑定矩阵" (00 §2.4) 的 Agent 行 风格一致.
 *
 * 视觉: 顶部彩色 accent 条 (跟书脊颜色一致) + 标题 + 元数据
 * 行 (label: value) + 进度条 + 操作按钮.
 */
import type { ReactNode } from "react";
import type { ShelfColorType } from "./index";
import { SHELF_COLORS } from "./index";

export type ShelfDetailPanelProps = {
  title?: string;
  subtitle?: string;
  /** 6 选 1 颜色 token, 跟书脊对齐 */
  accentColor?: ShelfColorType;
  /** 顶部 stats 行, {label, value} 数组 */
  stats?: Array<{ label: string; value: ReactNode }>;
  /** 主要操作按钮 (一个或多个) */
  actions?: ReactNode;
  /** 主体内容 (自由布局: log / 列表 / 子表格) */
  children?: ReactNode;
  emptyHint?: string;
};

export function ShelfDetailPanel({
  title,
  subtitle,
  accentColor = "blue",
  stats = [],
  actions,
  children,
  emptyHint,
}: ShelfDetailPanelProps) {
  const c = SHELF_COLORS[accentColor] ?? SHELF_COLORS.blue;
  return (
    <div
      className="shelf-detail-panel"
      style={{ ["--shelf-accent" as any]: c.spine, ["--shelf-glow" as any]: c.glow }}
    >
      <header className="shelf-detail-panel-head">
        <span className="shelf-detail-panel-bar" aria-hidden />
        <div className="shelf-detail-panel-titles">
          {title && <h3 className="shelf-detail-panel-title">{title}</h3>}
          {subtitle && <p className="shelf-detail-panel-sub">{subtitle}</p>}
        </div>
      </header>

      {stats.length > 0 && (
        <dl className="shelf-detail-panel-stats">
          {stats.map((s) => (
            <div key={s.label} className="shelf-detail-panel-stat">
              <dt>{s.label}</dt>
              <dd>{s.value}</dd>
            </div>
          ))}
        </dl>
      )}

      <div className="shelf-detail-panel-body">
        {children ?? (
          <div className="muted small" style={{ padding: "8px 0" }}>
            {emptyHint ?? "选择一本书 / 一个对象查看详情"}
          </div>
        )}
      </div>

      {actions && <footer className="shelf-detail-panel-actions">{actions}</footer>}
    </div>
  );
}
