/**
 * P0 重构 — 书架基础组件库
 *
 * 总纲 (00) + P0 阶段 (01) 决定: 项目 / 拆书 / 记忆库三大一级入口都
 * 改成「书架式」结构. 既然后面 P1-P3 都要用同一套书架视觉, 这里
 * 抽出 Shelf* 基础组件, 后续 P1+ 直接 import 复用, 不重复写 CSS.
 *
 * 组件清单 (P0 全建, 但只有 ShelfBreadcrumb 立刻被 ProjectPage
 * 真正用到 — 其它是建筑块, P1-P3 在项目/拆书/记忆书架里组装):
 *
 *   - ShelfBreadcrumb  面包屑 (← 返回书架 + 当前路径)
 *   - ShelfBook        书脊卡片 (单本/单项目/单记忆册的可视化)
 *   - ShelfRow         一排书架 (水平 + 可滚动)
 *   - ShelfLayout      三栏 (左 stats / 中 书架 / 右 详情)
 *   - ShelfToolbar     书架上方工具条 (搜索 + 过滤 + 新建)
 *   - ShelfSidePanel   左/右窄摘要卡
 *   - ShelfDetailPanel 右下大详情卡 (选中对象的所有元数据)
 *
 * 风格统一在 Shelf.css:
 *   暗色背景 + 木质横板 + 发光书脊 + 悬停上浮 + 状态标签
 *   6 个颜色 token: blue / gold / purple / green / red / gray
 *   (分别对应 主写 / 高完成度 / 运行中 / 健康 / 失败 / 归档)
 */
import "./Shelf.css";

export { ShelfBreadcrumb } from "./ShelfBreadcrumb";
export { ShelfBook } from "./ShelfBook";
export { ShelfRow } from "./ShelfRow";
export { ShelfLayout } from "./ShelfLayout";
export { ShelfToolbar } from "./ShelfToolbar";
export { ShelfSidePanel } from "./ShelfSidePanel";
export { ShelfDetailPanel } from "./ShelfDetailPanel";

export type ShelfColorType = "blue" | "gold" | "purple" | "green" | "red" | "gray";
export type ShelfSize = "small" | "normal" | "large";

/** 颜色 token 集中表 — 给 ShelfBook / ShelfDetailPanel / ShelfSidePanel
 *  共用, 改一处所有组件同步. 当前实现就是把 spec 里的语义颜色映射
 *  到具体 hex; 后续如果 tokens.css 提供官方变量, 改成读 var 即可. */
export const SHELF_COLORS: Record<
  ShelfColorType,
  { spine: string; glow: string; tint: string; label: string }
> = {
  // blue: 主写 / 正常 — 当前写作进行中, 蓝色冷静, 跟"流水作业"对应
  blue:   { spine: "#3a6ea5", glow: "rgba(58, 110, 165, 0.45)", tint: "rgba(58, 110, 165, 0.18)",  label: "进行中" },
  // gold: 高完成度 / 已完成 — 接近 100% 字数, 跟现有的 accent-gold 同源
  gold:   { spine: "#d6a64e", glow: "rgba(214, 166, 78, 0.45)",  tint: "rgba(214, 166, 78, 0.18)",   label: "已完成" },
  // purple: 运行中 / 深度处理 — 拆书/DeepStudy/讨论室 进行中
  purple: { spine: "#a078c8", glow: "rgba(160, 120, 200, 0.45)", tint: "rgba(160, 120, 200, 0.18)",  label: "运行中" },
  // green: 健康 / 已通过 — 验收通过 / critic pass
  green:  { spine: "#5d9c5d", glow: "rgba(93, 156, 93, 0.45)",  tint: "rgba(93, 156, 93, 0.18)",    label: "通过" },
  // red: 失败 / 待修 — pipeline 失败, 待人工 review
  red:    { spine: "#c45858", glow: "rgba(196, 88, 88, 0.45)",   tint: "rgba(196, 88, 88, 0.18)",    label: "待修" },
  // gray: 归档 / 禁用 — 草稿/已归档/未启用
  gray:   { spine: "#6e7681", glow: "rgba(110, 118, 129, 0.40)", tint: "rgba(110, 118, 129, 0.15)",  label: "归档" },
};
