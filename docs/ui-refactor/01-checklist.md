# UI 重构 — Phase 验收清单

> 每个 Phase 收尾前**必须**过完对应章节的所有 checkbox。
> 任意一条不通过 = Phase 不收, 写偏差到 `02-risk-log.md`。
> 跨 Phase 的"小尾巴"放进 `09-followups.md` (Phase 8 时建)。

---

## Phase 0 — 基线保护 (本次目标)

- [x] `00-baseline.md` 写完 (页面清单 / 文件字数 / token 现状)
- [x] `01-checklist.md` 写完 (本文档)
- [x] `02-risk-log.md` 写完 (空模板 + 已知风险登记)
- [x] `package.json` 加 devDependencies: `@playwright/test`, `axe-core` (仅装, 不跑)
- [x] `.gitignore` 加 `playwright-report/` + `test-results/` (防误推)
- [x] `docs/ui-refactor/03-smoke-test-spec.md` 写完 (Phase 9 跑, 标好预期截图)
- [ ] **`git tag pre-ui-refactor` 打 tag** (Phase 0 收尾)
- [ ] **Playwright 装包** (`pnpm install` 通过, 不跑)

**Phase 0 收尾条件**: 全部 ✓ + 用户口头确认可以进入 Phase 1。

---

## Phase 1 — Token + 全局 CSS 修复 (P0)

- [ ] `tokens.css` 增补 (按需):
  - [ ] `--color-success-soft` / `--color-warning-soft` / `--color-error-soft` 语义别名
  - [ ] `--shadow-color` / `--focus-ring` 给 Phase 6 用
- [ ] `global.css` 修复:
  - [ ] `button` 默认 radius 改 `var(--radius)`
  - [ ] `.card` 默认 radius 改 `var(--radius-md)`, 加 `box-shadow: var(--shadow)` 已存在
  - [ ] `.card.dense` 子类 (14px padding, 12px margin) 替换所有 `<div className="card dense">` 用法
  - [ ] `.pill` 状态色映射统一化 (`.succeeded` / `.failed` / `.paused` / `.idle`)
- [ ] **全局 grep 硬编码 8px 圆角位置** → 0 个
- [ ] **全局 grep 硬编码 12px 圆角位置** → 0 个
- [ ] **`.text-muted` 改用 `var(--text-muted)` 确认** (现已统一)
- [ ] **对比度实测** (Playwright + axe-core, Phase 6 真正跑; Phase 1 用 0.5.4 WebAIM 估算 + 报告)
- [ ] **TS 编译通过** + **Vite 编译无 warning**
- [ ] **commit**: `chore(ui): Phase 1 — token + global CSS unification`

**Phase 1 收尾条件**: 全部 ✓ + `git diff` 0 个 `!important` 增加 (净下降或持平)。

---

## Phase 2 — AppShell 布局稳定化 (P0)

- [ ] **删 `display: block !important` + 末尾 "Final placement guard" 段**
- [ ] 统一媒体查询到 1 段 (line 401 + line 712 合并)
- [ ] 媒体查询内不出现 `!important`
- [ ] **手动验证 3 个断点**:
  - [ ] 1440×900 (默认, 4 区都显示)
  - [ ] 1024×768 (`max-width: 1100`, projectnav + chief 隐藏)
  - [ ] 375×812 (移动, 仅 rail + main)
- [ ] 滚动: 主内容区鼠标滚轮工作 (R15 fix 验证)
- [ ] `chief-recover-fab` 仍能恢复完全隐藏的 chief 面板
- [ ] `skip-link` Tab 焦点可访问
- [ ] **commit**: `refactor(ui): Phase 2 — AppShell 4-zone grid stable`

**Phase 2 收尾条件**: 全部 ✓ + `AppShell.css` 的 `!important` 数从 60+ 降到 < 5。

---

## Phase 3 — 统一 UI 组件库 (P1)

- [ ] `src/components/ui/` 目录新建
- [ ] **基础组件** (8 个):
  - [ ] `Button.tsx` — variants: primary / secondary / ghost / danger, sizes: sm / md / lg, loading 状态
  - [ ] `Card.tsx` — `Card.Header` / `Card.Body` / `Card.Footer` slots
  - [ ] `Input.tsx` — text / number / search, prefix / suffix icon
  - [ ] `Badge.tsx` — color variants (ok / warn / error / info / neutral)
  - [ ] `Skeleton.tsx` — 矩形/圆形/文本三形态
  - [ ] `EmptyState.tsx` — icon + title + description + optional action
  - [ ] `ErrorState.tsx` — 标题 + 详情 + 重试按钮
  - [ ] `Spinner.tsx` — 尺寸 + 颜色 variants
- [ ] `index.ts` barrel export
- [ ] **单元测试** (Vitest, 至少 Button + Card 一个 smoke test)
- [ ] **试点替换**: `pages/Dashboard.tsx` 至少 5 处用 `<Card>` 替换裸 `<div className="card">`
- [ ] **不动的**:
  - [ ] 14 个业务目录 (chapter / projects / tasks / ...)**不动** — 留给 Phase 8
- [ ] **commit**: `feat(ui): Phase 3 — unified component library + Dashboard trial`

**Phase 3 收尾条件**: 8 个组件 + Dashboard 试点 + Storybook (或 demo page) 跑通 + 0 现有 page 崩溃。

---

## Phase 4 — 状态体验 (P1)

- [ ] `EmptyState` / `ErrorState` / `Skeleton` 全部用上
- [ ] **识别 + 替换**:
  - [ ] "暂无数据" 文本 → `<EmptyState>`
  - [ ] `{loading && <Spinner/>}` → `<Skeleton count={n}/>`
  - [ ] 异常 UI → `<ErrorState onRetry={...} />`
- [ ] **错误边界** `src/components/ErrorBoundary.tsx` 新建
- [ ] **commit**: `feat(ui): Phase 4 — skeleton/empty/error states`

**Phase 4 收尾条件**: 跨 5+ page 使用, 没有任何裸 "暂无数据" / "加载失败" 字符串。

---

## Phase 5 — 动效 (P1)

- [ ] 装 `framer-motion` (已在 Phase 0 加到 devDependencies, 这步 `pnpm install`)
- [ ] 路由切换 fade transition
- [ ] 模态进出 scale + opacity
- [ ] 列表项 hover micro-interaction
- [ ] `prefers-reduced-motion` 关闭所有动画
- [ ] **commit**: `feat(ui): Phase 5 — motion system`

**Phase 5 收尾条件**: 用户演示 5 种动效 + 关掉 reduced-motion 后全停。

---

## Phase 6 — 可访问性 (P1)

- [ ] 装 `axe-core` + `@axe-core/playwright` (Phase 0 已加)
- [ ] **基础 a11y**:
  - [ ] 所有 button 有 `aria-label` 或可见文字
  - [ ] 所有 icon-only button 有 `aria-label`
  - [ ] 所有 form input 有 `<label>` 或 `aria-label`
  - [ ] 所有 modal 有 `role="dialog"` + `aria-modal="true"` + 焦点陷阱
  - [ ] 焦点环可见 (`--focus-ring` token)
- [ ] **键盘导航**: Tab 顺序合理, Esc 关弹窗, Enter 提交表单
- [ ] **色盲模拟** (Chrome DevTools): 主流程仍可区分
- [ ] **axe-core 报告**: 严重 violation 0 个, 中等 ≤ 5
- [ ] **commit**: `feat(a11y): Phase 6 — keyboard + screen reader support`

**Phase 6 收尾条件**: axe-core 严重 0 + 中等 ≤ 5 + 键盘能走通 1 条主流程。

---

## Phase 7 — 性能 (P2)

- [ ] **路由级 code splitting**: `React.lazy()` for 5+ 不常访问的 page
- [ ] **虚拟列表**: 任何 > 100 行的列表用 `react-window` 或 `react-virtuoso`
- [ ] **图片 lazy load**: `<img loading="lazy">` 或 `react-lazy-load-image-component`
- [ ] **bundle size**: Vite build 输出 < 1 MB (gzipped)
- [ ] **首屏 LCP** < 2.5s (Chrome DevTools Lighthouse)
- [ ] **commit**: `perf(ui): Phase 7 — code splitting + virtualization`

**Phase 7 收尾条件**: Lighthouse 分数 ≥ 90 (Performance) + bundle < 1MB。

---

## Phase 8 — 页面级重构 (P0-P2)

- [ ] **排期顺序** (按访问频度 + 复杂度):
  - [ ] Dashboard (P1)
  - [ ] ProjectsPage + ProjectPage (P0)
  - [ ] TasksPage (P0)
  - [ ] WorkerPage (P1)
  - [ ] PromptsPage (P1)
  - [ ] GraphPage + GraphsPage + GraphNetworkPage (P2)
  - [ ] MemoryShelfPage + MemoryPage (P2)
  - [ ] StudyPage + StudyLibraryPage (P2)
  - [ ] DiscussionPage + ReviewCommentsPage (P2)
  - [ ] ReaderAgentsPage + ReaderAgentDetailPage (P2)
  - [ ] AuditLogPage + AutomationAuditPage (P2)
  - [ ] GenrePromptMatrixPage (P2)
  - [ ] BehaviorPage (P2)
  - [ ] ChapterDetail (P2)
  - [ ] NotFound (P0, 单独一个 commit)
- [ ] 每个 page 一个 commit, 跨 page 改动拆开
- [ ] **commit 模板**: `refactor(ui/<page>): Phase 8 — <page> 接入 UI 组件库 + 状态体验`

**Phase 8 收尾条件**: 全部 page 替换完成 + `grep "className=.\"card" 0 处` (除 Phase 1 留的兼容类)。

---

## Phase 9 — 测试与验收 (P0-P2)

- [ ] **Playwright 配置**: `playwright.config.ts` + `e2e/` 目录
- [ ] **smoke test** (5 个核心流程):
  - [ ] 启动 → 看到 Dashboard
  - [ ] 创建项目 → 进入项目
  - [ ] 添加 Provider → 跑健康检查
  - [ ] 一键自动配置 → 19 个 Agent 分配
  - [ ] 删除 Provider → 二次确认弹窗 → 物理删除
- [ ] **layout test** (5 个断点 × 3 个 page):
  - [ ] 1440 / 1024 / 768 / 375 × Dashboard / ProjectPage / TasksPage
  - [ ] 视觉回归: 截图比对 baseline (Phase 0 拍的)
- [ ] **a11y test** (Playwright + axe-core):
  - [ ] Dashboard, ProjectPage, TasksPage, ModelConfigPage 严重 violation 0
- [ ] **Visual regression** (Playwright `toHaveScreenshot()`):
  - [ ] 3 套 baseline (1440/1024/375) × 3 核心 page
- [ ] **commit**: `test(ui): Phase 9 — Playwright e2e + visual + a11y`

**Phase 9 收尾条件**: 全部测试通过 + 5 个 smoke + 9 套 layout 截图全过 + axe 严重 0。

---

## 跨 Phase 不变量

任何 Phase **不许**:
- ❌ 改后端 API 合约
- ❌ 改路由表
- ❌ 改 Zustand store schema
- ❌ 改 Provider / Context 接口

任何 Phase **必须**:
- ✅ 每个独立 commit
- ✅ 跑 TS 0 错
- ✅ 跑 Vite build 0 warning
- ✅ 跑现有 31 个 page 还能加载 (dev server smoke)
- ✅ 截图前后对比写进 commit body
