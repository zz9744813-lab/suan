# UI 重构 — Phase 0 基线快照

> 创建时间: 2026-06-07
> 目的: 在动手改任何 UI 代码之前, 用数字记录**"重构前"的状态**, Phase 9 验收时同口径比对。
> 注意: 此文件只读快照, 禁止编辑历史数据 — 如需重测请新建一个时间戳文件。

---

## 1. 仓库结构

```
frontend/src/
├── pages/            31 个 .tsx 页面
├── styles/            2 个全局 css (global.css + tokens.css)
├── components/
│   ├── chapter/       章节相关
│   ├── dashboard/     工作台
│   ├── layout/        布局 (AppShell, RailNav 等)
│   ├── model-observability/   模型观测
│   ├── models/        模型管理
│   ├── project/       项目单页
│   ├── projects/      项目列表
│   ├── prompts/       Prompt
│   ├── reviews/       评论评审
│   ├── shelf/         记忆架
│   ├── study/         拆书
│   ├── tasks/         任务
│   ├── worker/        Worker
│   ├── AppShell.tsx + AppShell.css
│   └── ChiefAgentPanel.tsx
├── api/               API 客户端
├── types/             TS 类型
├── stores/            Zustand stores
├── hooks/             React hooks
└── ...
```

> **结论**: 组件按**业务域**组织, **没有** `src/components/ui/` 通用基础组件库。
> Phase 3 目标就是建立这一层。

---

## 2. 关键文件字数

| 文件 | 行数 | 字节数 | 备注 |
|---|---|---|---|
| `styles/tokens.css` | 109 | 4.0 KB | 已有完整设计 token (radius/font/color/size/z-index) |
| `styles/global.css` | ≥ 230 | ≥ 6 KB | 含 .card / .pill / .muted / .ok / .warn / .error |
| `components/AppShell.css` | 718 | 22 KB | **含 60+ 处 !important**, 末尾"Final placement guard" |
| `pages/Dashboard.tsx` | ~250 | 9.7 KB | 15 个 page 用了 .card, Dashboard.tsx 是其中之一 |
| `pages/ModelConfigPage.tsx` | ~520 | ~20 KB | 顶部按钮区, Provider 卡片行 (我之前 2026-06-07 改过) |

---

## 3. Design Token 现状

### 3.1 radius 体系 (在 `tokens.css`)

```css
--radius-sm:  4px;
--radius:     6px;   /* 基础 */
--radius-md:  8px;   /* 卡片 */
--radius-lg:  12px;  /* 面板 */
--radius-xl:  16px;  /* 弹窗 */
```

> ✅ **方案 P0 中"tokens.css 不存在 radius-md" 已不存在** — 体系完整, 不需要新建 token。
> 实际需要做的是确保**所有页面**使用 `var(--radius-md)` 而不是硬编码 8px。

### 3.2 颜色

```css
--bg-base/rail/panel/elevated/card/paper    /* 背景 7 档 */
--text-primary/secondary/muted/ink/ink-soft  /* 文字 5 档 */
--accent-gold/soft/dim                       /* 主色蓝, 旧名保留 */
--accent-violet/cyan                         /* 辅色 */
--state-ok/warn/error/info                   /* 语义 4 档 */
--nav-bg/bg2/ink/muted                       /* 深色面板 */
```

> ✅ token 体系**比方案描述的更完整**, Phase 1 不需要补 token, 只需要**修复**颜色值或加缺失的语义别名。

### 3.3 字体

```css
--font-sans:  "Inter", "PingFang SC", "Microsoft YaHei", -apple-system, ...
--font-serif: "Source Serif Pro", "Noto Serif SC", Georgia, serif;
--font-mono:  "JetBrains Mono", "Cascadia Code", Consolas, monospace;
```

> ✅ 字体栈已配全。

---

## 4. AppShell 现状分析

### 4.1 总体结构 (4-zone grid + 状态栏)

```
grid-template-columns: rail(56) | projectnav(260) | main(1fr) | chief(380)
grid-template-rows:    1fr | statusbar(28)
grid-template-areas:   "rail projectnav main chief"
                       "statusbar statusbar statusbar statusbar"
```

> R12.1 / P0-UI-7 已修复 statusbar 跨 4 列, ✅ 通过。

### 4.2 ⚠️ 关键 P0 问题

**`AppShell.css` line 586**:

```css
.app-shell,
.shell {
  display: block !important;     /* ← 覆盖 line 22 的 display: grid */
  position: fixed !important;
  inset: 0 !important;
  /* ... 共 14 个 !important ... */
}
```

**问题**: "Final placement guard" 段用 `display: block` **覆盖**了**开头的 `display: grid`**,
然后又对每个子区域用 `position: fixed` + `!important` 单独定位。

**结果**:
- grid 模板失效, 实际渲染靠 `position: fixed` 兜底
- 任何对 layout 的扩展(例如响应式断点)都得用 `!important` 覆盖回去
- 共 **60+ 个 `!important`** 散落在 AppShell.css

### 4.3 响应式断点重复

- line 401: `@media (max-width: 1100px) { grid-template-columns: var(--rail-width) 1fr; ... }`
- line 712: `@media (max-width: 1100px) { --projectnav-width: 0px; --chief-width: 0px; }`

> 两段语义有重叠, 实际**都被 `!important` 覆盖**, 不一定都生效。需要重构期统一。

### 4.4 修复方向 (Phase 2)

1. **删 `display: block !important`** + 全部固定定位, **回到纯 grid**。
2. 媒体查询用 grid-template-columns 控制, 不用 !important 覆盖。
3. 子区域保留 `grid-area` 即可, 不需要 fixed。

---

## 5. 现状对方案的偏差

| 方案假设 | 实际现状 | 处理方式 |
|---|---|---|
| `tokens.css` 不存在 `--radius-md` | **已存在** | ✅ 不需要新建, Phase 1 改为**修正引用** |
| `Dashboard` 用 `.card` 冲突全局 `.card` | Dashboard.tsx 在用 `.card` + `.dashboard-card` 混用 (待确认) | Phase 1 全局统一为 `.card`, 改局部为 `.dashboard-card` (仅 Dashboard) |
| `AppShell.css` 末尾有 `display:block !important` | **确实存在** | Phase 2 删 |
| 需要新建 `src/components/ui/` 基础组件库 | **不存在**, 现有 14 个目录都是业务组件 | Phase 3 新建 (Button, Card, Input, Badge, Skeleton, EmptyState, ErrorState, Spinner, Toast) |
| 需装 `framer-motion` / `playwright` / `axe-core` | **未装** | Phase 0 加 `package.json` devDependencies, Phase 5/6/9 真正使用 |
| `.muted` 对比度不够 | `--text-muted: #5f6b7a` (light), 注释里写"WCAG AA 4.54:1" | ✅ 注释声称达标, **需用工具实测** (Phase 1 + Phase 6) |

---

## 6. 统计指标 (验收用)

| 指标 | 当前值 | Phase 1 目标 | Phase 2 目标 | Phase 3 目标 |
|---|---|---|---|---|
| `AppShell.css` 内 `!important` 数 | 60+ | 60+ (不增加) | **< 5** | < 5 |
| 全局重复的 `@media` 段 | 2 | 2 | **1** | 1 |
| `src/components/ui/` 文件数 | 0 | 0 | 0 | **≥ 8** |
| `.card` 使用页面数 | 15 (全局唯一) | 15 (统一为 `var(--radius-md)`) | 15 | 13+ (剩 2+ 改用 `<Card>` 组件) |
| 硬编码 `8px` / `12px` 圆角位置 | 估算 30+ | 0 (全部 `var(--radius-*)`) | 0 | 0 |
| Playwright 用例数 | 0 | 0 | 0 | 0 → Phase 9 |
| axe-core violation 数 | 未测 | 未测 | 未测 | Phase 6 < 5 (严重 0) |

---

## 7. 现有 page 列表 (供 Phase 8 排期)

```
AgentMemoryPage.tsx
AuditLogPage.tsx
AutomationAuditPage.tsx
BehaviorPage.tsx
ChapterDetail.tsx
Dashboard.tsx             ← Phase 3 试点
DiscussionPage.tsx
GenrePromptMatrixPage.tsx
GraphNetworkPage.tsx
GraphPage.tsx
GraphsPage.tsx
MemoryPage.tsx
MemoryShelfPage.tsx
ModelConfigPage.tsx       ← 2026-06-07 改过, 保持
ModelProviderDetailPage.tsx ← 2026-06-07 改过, 保持
ModelsPage.tsx            ← 2026-06-07 改过, 保持
NotFound.tsx
ProjectPage.tsx
ProjectsPage.tsx
PromptsPage.tsx
ReaderAgentDetailPage.tsx
ReaderAgentsPage.tsx
ReviewCommentsPage.tsx
StudyLibraryPage.tsx
StudyPage.tsx
TasksPage.tsx
WorkerPage.tsx
```

---

## 8. 检查清单 (Phase 0 验收)

- [x] 仓库结构清单 (第 1 节)
- [x] 关键文件字数 (第 2 节)
- [x] Token 现状评估 (第 3 节)
- [x] AppShell 现状分析 (第 4 节)
- [x] 方案偏差报告 (第 5 节)
- [x] 统计指标 (第 6 节)
- [x] 页面列表 (第 7 节)
- [ ] **Playwright + axe-core 装包** (Phase 0 任务 0.3.2, 待 Phase 0.4 完成)
- [ ] **smoke 截图基线** (Phase 0 任务 0.4, 待跑过)
- [ ] **git tag 标记** (建议: `git tag pre-ui-refactor`, Phase 0 收尾时打)
