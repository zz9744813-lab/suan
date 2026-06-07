# UI 重构 — 风险日志

> 任何跨 Phase 决策/踩坑登记在这里, 不要写在 commit body 里 (commit body 容易被 `git log` 吞掉)。
> 格式: 日期 | 风险 | 影响 | 处理 | 状态

---

## R-001 [Phase 0] 2026-06-07

- **风险**: `AppShell.css` 末尾 60+ 处 `!important` 是**有意的**"Final placement guard", 删了可能回归旧 bug。
- **影响**: 删后任何 `display: flex` / `display: block` 的旧代码会破坏 grid。
- **处理**:
  - Phase 2 删前先**逐处** grep 当前所有 `display: ... !important` 来源
  - 删后**逐个 page** 跑 dev server smoke (脚本化, 9 套截图)
  - 一旦回归, 立即 `git revert`, 不在 main 上 hotfix
- **状态**: Open (Phase 0 登记, Phase 2 处理)

---

## R-002 [Phase 0] 2026-06-07

- **风险**: `.card` 在 `global.css` 是**全局唯一**, 但 15 个 page 在用。Phase 1 改 `.card` 会牵一发动全身。
- **影响**: 任何 padding / radius / shadow 调整会让 15 个 page 同时变样, 视觉回归风险。
- **处理**:
  - Phase 1 **只** 改 `.card` 默认 padding/radius (用 `var(--radius-md)`), 不动 padding (16px → 14px 是 Phase 8 试点 page 决定)
  - 不在 `.card` 加新功能, 全部用 `.card.dense` 等子类
  - Phase 8 试点 page 改用 `<Card>` 组件, **不**删 `.card` 类 (向后兼容)
- **状态**: Open (Phase 0 登记, Phase 1+8 处理)

---

## R-003 [Phase 0] 2026-06-07

- **风险**: `AppShell.css` line 401 + line 712 有重复的 `@media (max-width: 1100px)`, 合并时第二段被 `!important` 覆盖可能失效。
- **影响**: 移动断点行为可能不同 (projectnav/chief 隐藏时机不对)。
- **处理**:
  - Phase 2 删前先**手动**测 3 个断点截图存 baseline
  - 删后**逐个**断点比对
  - 改用 `min-width: 1101px` 默认 / `max-width: 1100px` 媒体查询, 不混用
- **状态**: Open

---

## R-004 [Phase 0] 2026-06-07

- **风险**: Playwright + axe-core 是**新依赖**, 装包可能引入 node_modules 体积爆炸 (Playwright 单独 300MB+) 和版本冲突。
- **影响**: `pnpm install` 时间 +5min, 仓库 disk 占用 +400MB.
- **处理**:
  - 加 `package.json` devDependencies 时**显式**标 `^X.Y.Z` 锁定主版本
  - Playwright browsers 在 `npx playwright install` 时跳过 (`PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`), 留给 Phase 9 真用时再装
  - `playwright-report/` + `test-results/` 加 `.gitignore`
- **状态**: Open (Phase 0 装包时验证)

---

## R-005 [Phase 0] 2026-06-07

- **风险**: `ModelConfigPage.tsx` / `ModelProviderDetailPage.tsx` 我在 2026-06-07 改过 (auto-configure / MonitorBanner), 它们的样式用**内联** style + 部分 `className="card"`, 重构期会**冲突**。
- **影响**: Phase 1 改 `.card` 不会影响内联 style, 但 Phase 3 `<Card>` 替换时需要**手动迁移**这两个 page。
- **处理**:
  - Phase 1 **不动** 这两个 page (它们不在 Phase 8 P0 排期)
  - Phase 8 把它们列在 P1 排期, 单独 commit
  - 如果用户优先要这两个 page 走 `<Card>`, Phase 8 提前
- **状态**: Open

---

## R-006 [Phase 0] 2026-06-07

- **风险**: 方案说"分阶段独立 commit", 但用户本次提交走的是 "1 个 commit", 前置 commit `9c09fbd` 已经把 2026-06-07 的所有改动**打包**推上 GitHub。后续 Phase commit 会**叠加**。
- **影响**: 用户如果 git reset 回到 9c09fbd, UI 重构的所有工作都丢。
- **处理**:
  - **Phase 0 收尾时**打 tag `pre-ui-refactor` 指向当前 HEAD (9c09fbd 或后续)
  - 任何 Phase 0+ 的 commit **不** amend 上一个 (保持历史清晰)
  - 如需 revert 整个 UI 重构, `git reset --hard pre-ui-refactor`
- **状态**: Open (Phase 0 收尾时打 tag)

---

## R-007 [Phase 0] 2026-06-07

- **风险**: 方案说 "**不重写后端**" 但我之前 commit 9c09fbd 含 backend 改动 (P-Delete-Preview / 5 schema 修复)。**这意味着 9c09fbd 提交事实上是 UI 重构的基线**, Phase 1 起的 commit 不应再含 backend 改动。
- **影响**: 重构期间混 backend 改动, 很难 cherry-pick / revert。
- **处理**:
  - Phase 1+ commit scope **强制限定** `frontend/src/` + `docs/ui-refactor/` + `package.json` + `playwright.config.ts` + `frontend/src/styles/`
  - 不碰 `backend/` `/` `frontend/src/api/` (API client 也不改, 除非 Phase 1 必然需要的 type)
  - 任何"顺手" backend fix 单独 commit, 标 `[out-of-scope]`
- **状态**: Open (执行期监督)

---

## R-008 [Phase 0] 2026-06-07

- **风险**: 31 个 page 中 4 个有同名 `.css` 文件 (`Dashboard.css` / `DiscussionPage.css` / `MemoryPage.css` / `ReviewCommentsPage.css` / `StudyPage.css` / `GenrePromptMatrixPage.css` / `TasksPage.css`), Phase 1 改 `global.css` 影响这些 page 的级联优先级, 容易引发特异性 (specificity) 战争。
- **影响**: 改 `.card` 可能在 Dashboard 走 `Dashboard.css` 的 `.card` 覆盖, 行为不一致。
- **处理**:
  - Phase 1 改前先 `cat Dashboard.css | grep -A5 '^\.card'` 抓 4 个 page 各自 `.card` 定义
  - 用 `git diff main` 看变更范围, 任何 1 个 page 的 `.card` 视觉变化**单独** 报告
  - Phase 8 page 改造时把同名 css 移入 page 内部 (`pages/Dashboard.css` → `pages/Dashboard/Dashboard.module.css` 等)
- **状态**: Open

---
