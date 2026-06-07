# UI 重构 — Smoke 测试规格 (Phase 9 用)

> 这是 Phase 9 要跑的测试规格, Phase 0 阶段**只写不跑**。
> 每条测试有: 步骤 / 预期结果 / 视觉基线位置。

---

## 浏览器/工具版本

- Chromium (Playwright 自带, `npx playwright install chromium`)
- 视口默认: 1440×900 (desktop)
- Theme: 默认 light
- 启动: `pnpm dev` 同时跑 backend (8000) + frontend (5173)

---

## T-SMOKE-01: 启动 → Dashboard 加载

- **步骤**:
  1. `cd frontend && pnpm dev`
  2. `cd backend && python -m uvicorn app.main:app --reload --port 8000`
  3. `pnpm test:e2e tests/smoke/01-boot.spec.ts` (Phase 9 写)
- **预期**:
  - [ ] `/` → 重定向 `/projects` 或 `/dashboard`
  - [ ] 看到 4-zone grid (rail / projectnav / main / chief)
  - [ ] 状态栏 28px, 看到 "Worker: idle"
  - [ ] console 0 错 0 警 (除了 `getThemeColors` 已知问题)
- **视觉基线**: `docs/ui-refactor/screenshots/baseline/01-boot-1440.png`

---

## T-SMOKE-02: 创建项目

- **步骤**:
  1. `/projects` 看到列表
  2. 点击 "新建项目"
  3. 输入名称, 选流派, 提交
- **预期**:
  - [ ] 弹窗 dialog 有 `role="dialog"` + `aria-modal="true"`
  - [ ] 提交后路由 `/projects/<new-id>`
  - [ ] projectnav 出现新项目, active state 高亮
- **视觉基线**: `02-create-project-{before,after}.png`

---

## T-SMOKE-03: 添加 Provider + 健康检查

- **步骤**:
  1. `/models` 点击 "添加 API Provider"
  2. 填表: name=`test`, base_url=`http://127.0.0.1:9` (故意不可达)
  3. 提交
  4. 在新 Provider 行点击 "健康检查"
- **预期**:
  - [ ] 新行出现在列表
  - [ ] "健康检查" 按钮变 "检查中..." → 完成后 200ms 内还原
  - [ ] 失败行 failing_count=1, healthy_count=0
  - [ ] 全局 4 个统计卡实时刷新
- **视觉基线**: `03-add-provider.png`

---

## T-SMOKE-04: 一键自动配置

- **步骤**:
  1. `/models` 点击 "一键自动配置"
  2. 弹窗显示系统推荐 (Provider/Model 列表)
  3. 点击 "使用推荐配置"
- **预期**:
  - [ ] 弹窗出现 + 列出 ≥ 10 个 Agent 的推荐分配
  - [ ] 点击确认后弹窗消失
  - [ ] 底部 Agent 状态区**所有**"自动模式" Agent 显示具体 provider/model
  - [ ] 锁定 AGENT 数量保持不变
  - [ ] POST `/api/agent-roles/auto-configure` 200, network log 可见
- **视觉基线**: `04-auto-configure.png`

---

## T-SMOKE-05: 删除 Provider

- **步骤**:
  1. `/models` 选一个 stub 或无绑定的 Provider
  2. 点击 "删除"
  3. 弹窗: 显示 danger_level + 角色绑定 + 历史调用统计
  4. 确认删除
- **预期**:
  - [ ] 弹窗颜色随 danger_level 变 (safe=绿, caution=黄, danger=红)
  - [ ] 确认后 Provider 行消失
  - [ ] 4 个统计卡实时刷新
  - [ ] GET `/api/models/providers/<id>/delete-preview` 200 (弹窗打开时调)
  - [ ] DELETE `/api/models/providers/<id>` 200 (确认时调)
- **视觉基线**: `05-delete-provider-{safe,caution,danger}.png`

---

## T-LAYOUT-01 × 03: 布局断点

| 视口 | Page | 视觉基线 |
|---|---|---|
| 1440×900 | Dashboard | `layout-01-dashboard-1440.png` |
| 1440×900 | ProjectPage | `layout-02-project-1440.png` |
| 1440×900 | TasksPage | `layout-03-tasks-1440.png` |
| 1024×768 | Dashboard | `layout-04-dashboard-1024.png` |
| 1024×768 | ProjectPage | `layout-05-project-1024.png` |
| 1024×768 | TasksPage | `layout-06-tasks-1024.png` |
| 375×812 | Dashboard | `layout-07-dashboard-375.png` |
| 375×812 | ProjectPage | `layout-08-project-375.png` |
| 375×812 | TasksPage | `layout-09-tasks-375.png` |

**预期**:
- [ ] 1440 / 1024: rail + projectnav + main + chief 4 区
- [ ] 1024 ≤ 1100: projectnav + chief 隐藏, chief-recover-fab 出现
- [ ] 375: 仅 rail + main, 移动菜单 burger 出现

---

## T-A11Y-01: axe-core 严重违规

- **步骤**:
  1. 跑 `pnpm test:a11y tests/a11y/01-core.spec.ts`
  2. 4 个核心 page: Dashboard / ProjectPage / TasksPage / ModelConfigPage
- **预期**:
  - [ ] 严重 violation 0
  - [ ] 中等 violation ≤ 5
  - [ ] 轻微 violation 在文档登记, 后续清理

---

## T-MOTION-01: 动效与 prefers-reduced-motion

- **步骤**:
  1. 默认 Chromium (动效开)
  2. 路由切换 / 模态进出 / 列表 hover
  3. `page.emulateMedia({ reducedMotion: 'reduce' })` 后重跑
- **预期**:
  - [ ] 动效开: 看到 fade / scale / 微交互
  - [ ] 动效关: 切换是瞬间, 无 transition

---

## T-PERF-01: Lighthouse 分数

- **步骤**:
  1. `pnpm build` → `pnpm preview`
  2. Chrome DevTools → Lighthouse → Performance / Accessibility / Best Practices
- **预期**:
  - [ ] Performance ≥ 90
  - [ ] Accessibility ≥ 90
  - [ ] Best Practices ≥ 90
  - [ ] LCP < 2.5s
  - [ ] bundle gzipped < 1MB

---

## 视觉基线存放路径

```
docs/ui-refactor/screenshots/
└── baseline/
    ├── 01-boot-1440.png
    ├── 02-create-project-before.png
    ├── 02-create-project-after.png
    ├── 03-add-provider.png
    ├── 04-auto-configure.png
    ├── 05-delete-provider-safe.png
    ├── 05-delete-provider-caution.png
    ├── 05-delete-provider-danger.png
    ├── layout-01-dashboard-1440.png
    ├── layout-02-project-1440.png
    ├── layout-03-tasks-1440.png
    ├── layout-04-dashboard-1024.png
    ├── layout-05-project-1024.png
    ├── layout-06-tasks-1024.png
    ├── layout-07-dashboard-375.png
    ├── layout-08-project-375.png
    └── layout-09-tasks-375.png
```

> 基线**只**在 Phase 9 拍, **不要**提前拍 (避免 Phase 0 还在改, baseline 不准)。
> 用 `playwright.config.ts` 的 `toHaveScreenshot()` 跑回归。
