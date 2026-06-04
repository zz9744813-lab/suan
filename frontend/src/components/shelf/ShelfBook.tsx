/**
 * ShelfBook — 书脊卡片
 *
 * P0 §4.3: 项目、参考书、记忆册都使用同一个书脊基础组件.
 * Spec 定义的 props (P0 §4.3 + §5 颜色表):
 *
 *   title          必填, 书脊上印的字
 *   subtitle       副标题 (作者 / 来源 / 册号)
 *   status         右上角状态文字 (运行中 / 已完成 / 待修 / ...)
 *   progressLabel  进度文本 (例 "12/30 章节")
 *   colorType      6 选 1 (blue/gold/purple/green/red/gray) — 书脊主色
 *   size           3 选 1 (small/normal/large) — 书架密度自适配
 *   selected       是否被选中, 选中加金色描边
 *   onClick        点击 → 跳二级工作台
 *
 * 视觉: 垂直书脊 (height > width, 文字竖排但单行), 顶部 spine
 * 颜色 + spine glow 投影; 底部进度条 + 状态标签; hover 时书脊
 * 微微上浮 2px + glow 增强.
 */
import type { ShelfColorType, ShelfSize } from "./index";
import { SHELF_COLORS } from "./index";

export type ShelfBookProps = {
  title: string;
  subtitle?: string;
  status?: string;
  /** 0~100, 渲染底部进度条 */
  progressPct?: number;
  progressLabel?: string;
  colorType?: ShelfColorType;
  size?: ShelfSize;
  selected?: boolean;
  onClick?: () => void;
  /**
   * 悬停提示 (HTML 原生 title 属性). P1 项目书架: 章节进度 / 最近
   * 任务 / Worker 状态等都通过这个 prop 一次性传进来, 鼠标悬停即看.
   * 不引入额外 popover 组件 — P0 §8 禁 6 (不过度工程), 原生 tooltip
   * 在桌面端够用, 移动端 long-press 也会触发.
   */
  hoverHint?: string;
};

const SIZE_PX: Record<ShelfSize, { w: number; h: number; spineW: number; fontSize: number }> = {
  // small:  抽屉里一格 (列表用), 72x130
  small:  { w: 72,  h: 130, spineW: 8,  fontSize: 11 },
  // normal: 书架上正常书 (项目/参考书), 96x180
  normal: { w: 96,  h: 180, spineW: 10, fontSize: 13 },
  // large:  记忆册 / 大型对象, 128x220
  large:  { w: 128, h: 220, spineW: 12, fontSize: 15 },
};

export function ShelfBook({
  title,
  subtitle,
  status,
  progressPct,
  progressLabel,
  colorType = "blue",
  size = "normal",
  selected = false,
  onClick,
  hoverHint,
}: ShelfBookProps) {
  const dim = SIZE_PX[size];
  const c = SHELF_COLORS[colorType] ?? SHELF_COLORS.blue;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`shelf-book shelf-book--${size} ${selected ? "is-selected" : ""}`}
      style={{
        width: dim.w,
        height: dim.h,
        // CSS variable 给 .shelf-book::after (顶部 spine) 和
        // ::before (底部投影) 共用, 改 colorType 不需要重写 CSS
        ["--shelf-spine" as any]: c.spine,
        ["--shelf-glow"  as any]: c.glow,
        ["--shelf-tint"  as any]: c.tint,
        ["--shelf-font"  as any]: `${dim.fontSize}px`,
      }}
      aria-label={`${title}${status ? ` (${status})` : ""}`}
      title={hoverHint}
    >
      <span className="shelf-book-status" style={{ background: c.tint, color: c.spine }}>
        {status ?? c.label}
      </span>
      <span className="shelf-book-title">{title}</span>
      {subtitle && <span className="shelf-book-subtitle">{subtitle}</span>}
      {progressPct != null && (
        <span className="shelf-book-progress">
          <span
            className="shelf-book-progress-fill"
            style={{ width: `${Math.max(0, Math.min(100, progressPct))}%` }}
          />
        </span>
      )}
      {progressLabel && <span className="shelf-book-progress-label">{progressLabel}</span>}
    </button>
  );
}
