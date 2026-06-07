# UI Baseline

## 页面清单

| 页面 | 路由 | 关键组件 | 当前主要问题 | 后端依赖 | 长列表 | 弹窗/抽屉 | 移动端适配 |
|---|---|---|---|---|---|---|---|
| Dashboard | `/dashboard` | DashboardStatusBar, CurrentPipelinePanel, FailureDiagnosisCard, ChapterPreviewCard, UsefulEventStream, PassFailRateCard, DashboardKpiCards, AgentPipelineVisualization, MemoryLayerCard, ReaderFeedbackPanel, DiscussionLoopCard, SkillGeneratedCard | .card 与 global.css 冲突 | 是 | 否 | 否 | 部分 |
| ProjectsPage | `/projects` | Shelf, ShelfBook, CreateProjectDialog | 无 | 是 | 是 | 是(新建项目) | 部分 |
| ProjectPage | `/projects/:pid` | — | .card 全局样式依赖 | 是 | 是 | 否 | 部分 |
| ChapterDetail | `/projects/:pid/chapters/:cid` | — | .card 全局样式依赖 | 是 | 否 | 否 | 否 |
| WorkerPage | `/worker` | — | .card 全局样式依赖 | 是 | 是 | 否 | 否 |
| TasksPage | `/tasks` | CommandCenterPanel | 长列表无虚拟化 | 是 | 是 | 否 | 部分 |
| PromptsPage | `/prompts` | — | .card 全局样式依赖 | 是 | 否 | 是 | 否 |
| ModelConfigPage | `/models` | ProviderAccordion, AgentRoleMatrix, AutoConfigureModal | 复杂嵌套 | 是 | 否 | 是 | 否 |
| ModelProviderDetailPage | `/models/providers/:providerId` | — | — | 是 | 否 | 否 | 否 |
| StudyLibraryPage | `/study/library` | AddBookModal, StudyShelfView | 48KB 大组件 | 是 | 是 | 是 | 部分 |
| StudyPage | `/study/upload` | — | .card 全局样式依赖 | 是 | 否 | 否 | 否 |
| BehaviorPage | `/behavior` | — | global.css 内联样式 | 是 | 否 | 否 | 否 |
| GraphsPage | `/graphs` | — | .card 全局样式依赖 | 是 | 否 | 否 | 否 |
| GraphPage | `/graph/:id` (redirect) | — | 54KB 大组件, SVG 撑爆容器 | 是 | 否 | 否 | 否 |
| GraphNetworkPage | `/graphs/:materialId/network` | — | — | 是 | 否 | 否 | 否 |
| DiscussionPage | `/discussion` | — | 11KB CSS | 是 | 是 | 否 | 否 |
| AgentMemoryPage | `/memory` | — | — | 是 | 否 | 否 | 否 |
| MemoryShelfPage | `/memory-shelf` | — | 47KB 大组件 | 是 | 是 | 否 | 部分 |
| ReviewCommentsPage | `/reviews` | — | — | 是 | 否 | 否 | 否 |
| ReaderAgentsPage | `/reader-agents` | — | — | 是 | 否 | 否 | 否 |
| GenrePromptMatrixPage | `/prompts-matrix` | — | 9KB CSS | 是 | 否 | 否 | 否 |
| AutomationAuditPage | `/audit` | — | — | 是 | 否 | 否 | 否 |
| AuditLogPage | `/audit-logs` | — | — | 是 | 否 | 否 | 否 |

## AppShell 结构

```
┌──[RailNav 56px]──[ProjectNav 260px]──[Main]──[ChiefPanel 380px]──┐
└─────────────────────[BottomStatusBar 28px]───────────────────────┘
```

- 三模式面板: expanded / compact / hidden
- Final placement guard: `display: block !important` 覆盖 grid
- 响应式断点: 仅 1100px (硬切换)
- 移动端: 无底部导航, RailNav 仍显示

## 已修复项

- `--radius-md: 8px` 已存在于 tokens.css
- `--text-muted: #5f6b7a` 已满足 WCAG AA
- `--state-ok: #168a6b` 已满足 WCAG AA

## 待修复项

- [P0-02] `.card` 全局冲突 (Dashboard.css vs global.css)
- [P0-03] AppShell `display: block !important` 覆盖 grid
- [P0-04] 移动端无底部导航, <860px 时 ProjectNav 消失但 RailNav 不消失
- [P1-01] 无统一 UI 组件库
- [P1-03] RailNav 使用 emoji 图标
