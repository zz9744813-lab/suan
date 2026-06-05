# P0 技术方案：真实 API Provider / Model 配置与切换

> 问题：当前所有 Agent 绑定的是 `stub` Provider 和 `mock-*` 模型，需要能够配置真实的外部 API（OpenRouter、DeepSeek、Gemini 等）并切换到真实环境运行。

---

## 0. 当前问题诊断

| 问题 | 现象 | 根因 |
|---|---|---|
| 所有 Agent 使用 stub | Provider: stub, Model: mock-fast | 没有配置真实 Provider，系统默认回到 stub |
| Provider 列表只有 stub | 左侧只有 stub 手风琴 | 数据库没有真实 Provider 记录 |
| 健康检查显示正常 | 1h 成功率 100%，延迟 170ms | 这是 stub 自检，不是真实 API |

**结论**：已有 Provider 管理 UI 和 Agent 模型绑定 UI，但缺少"配置真实 Provider"的引导流程。

---

## 1. P0-A：首次引导弹窗

### 当前问题
用户进入 `/models` 页面，看到 Provider 列表只有一个 `stub`，不知道如何添加真实 API。

### 方案
检测到只有 stub Provider 时，弹出引导：

```
┌─────────────────────────────────────────────────────┐
│  欢迎使用 NovelForge 模型配置                        │
│                                                      │
│  当前系统使用 mock 模式运行，仅用于开发测试。         │
│  要开始真实写作，请添加至少一个外部 API Provider。   │
│                                                      │
│  [快速添加 OpenRouter]   [快速添加 DeepSeek]         │
│  [手动配置]                                          │
│                                                      │
│  ℹ️ 推荐 OpenRouter，支持 Claude/GPT/Gemini 多模型  │
└─────────────────────────────────────────────────────┘
```

### 涉及文件
- `frontend/src/pages/ModelsPage.tsx` — 添加 useEffect 检测 + FirstRunGuide modal
- `frontend/src/components/models/FirstRunGuide.tsx` — 新建引导组件

---

## 2. P0-B：Provider 表单增强

### 当前问题
Provider 创建/编辑表单只有 4 个字段：name、base_url、enabled、api_key。缺少类型选择和模型拉取。

### 方案
增强 ProviderAccordion 表单：

```
名称: [OpenRouter                               ]
类型: [OpenRouter ▼] (选择后自动填充 base_url)
Base URL: [https://openrouter.ai/api/v1         ]
API Key:  [sk-or-v1-...           ] [显示/隐藏]
默认模型: [anthropic/claude-3.5-sonnet ▼]
模型列表: [已拉取 15 个模型] [刷新]

[🔍 测试连接]  [保存]
```

| 新增字段 | 说明 |
|---|---|
| 类型下拉 | OpenRouter / OpenAI / DeepSeek / Gemini / 自定义，选后自动填 base_url |
| 默认模型下拉 | 从 Provider 拉取的模型列表中选择 |
| 模型列表刷新 | 点击后调用 `/models/{name}` 拉取，支持手动输入 |
| 测试连接 | 发送 1 个 token 的真实请求验证 API Key |

### 涉及文件
- `frontend/src/components/models/ProviderAccordion.tsx` — 表单增强
- `frontend/src/api/index.ts` — 新增 getProviderModels API

---

## 3. P0-C：一键绑定真实模型

### 当前问题
添加了真实 Provider 后，用户还要手动去每个 Agent 的编辑弹窗绑定 Provider/Model，太麻烦。

### 方案
添加第一个真实 Provider 成功后，弹出「一键配置」：

```
┌─────────────────────────────────────────────────────┐
│  ✅ OpenRouter 已就绪                                 │
│                                                      │
│  检测到 15 个可用模型：                               │
│  · anthropic/claude-3.5-sonnet                      │
│  · openai/gpt-4o                                    │
│  · google/gemini-flash-1.5                          │
│  ...                                                 │
│                                                      │
│  推荐配置：                                          │
│  Planner     claude-3.5-sonnet   (规划能力强)        │
│  Draft       claude-3.5-sonnet   (写作质量高)        │
│  Critic      claude-3.5-sonnet   (评审严格)          │
│  Reader-A    gemini-flash-1.5    (速度快)            │
│  Reader-B    gemini-flash-1.5    (速度快)            │
│  ...                                                 │
│                                                      │
│  [✓ 使用推荐配置]  [手动调整]                         │
└─────────────────────────────────────────────────────┘
```

点击后自动调用 `PUT /api/agent-roles/{id}/model-binding` 为所有 Agent 绑定真实模型。

### 涉及文件
- `frontend/src/components/models/AutoConfigureModal.tsx` — 新建一键配置弹窗
- `frontend/src/pages/ModelsPage.tsx` — 添加 Provider 添加成功后的回调

---

## 4. P0-D：Stub 守卫

### 当前问题
即使 UI 做好了，如果用户没有绑定真实模型，Worker 仍然默默使用 stub 运行。

### 方案
1. **Agent 卡片警告**：绑定 stub 的 Agent 显示黄色警告条
2. **全局警告条**：超过 50% Agent 用 stub 时，页面顶部显示警告
3. **Worker 检查**：生产环境启动时，检测到有 Agent 用 stub 则报错

### Agent 卡片 stub 警告
```
┌──────────────────────────────────────────────┐
│  planner                          ⚠️ mock   │
│  stub / mock-fast                            │
│  ┌──────────────────────────────────────────┐│
│  │ ⚠️ 使用 mock 模型，请绑定真实 Provider   ││
│  │ [选择 Provider] [选择 Model]             ││
│  └──────────────────────────────────────────┘│
└──────────────────────────────────────────────┘
```

### 全局警告条
```
┌──────────────────────────────────────────────────────────────┐
│ ⚠️ 8/17 个 Agent 仍使用 mock 模型，生产写作不会调用真实 API │
│ [一键配置真实模型]                                      [×] │
└──────────────────────────────────────────────────────────────┘
```

### 涉及文件
- `frontend/src/components/models/AgentRoleMatrix.tsx` — Agent 卡片 stub 警告
- `frontend/src/App.tsx` 或 `ModelsPage.tsx` — 全局 stub 警告条

---

## 5. 执行顺序

| 阶段 | 内容 | 预计文件数 |
|---|---|---|
| **P0-A** | 首次引导弹窗 FirstRunGuide | 2 |
| **P0-B** | Provider 表单增强（类型下拉+模型列表+测试连接） | 2 |
| **P0-C** | 一键配置 AutoConfigureModal | 2 |
| **P0-D** | Stub 守卫（Agent 警告+全局警告条） | 2 |

---

## 6. 验收标准

| 验收项 | 标准 |
|---|---|
| 首次进入 | 看不到任何方法配置时，弹出引导添加 Provider |
| 添加 Provider | 3 步完成：输入 API Key → 测试连接 → 保存 |
| 一键配置 | 点击后所有写作 Agent 自动绑定真实模型 |
| Agent 卡片 | 使用真实 Provider/Model 的显示绿色 ✓，使用 stub 的显示黄色 ⚠️ |
| 全局警告 | 超过 50% Agent 用 stub 时显示全局警告条 |
