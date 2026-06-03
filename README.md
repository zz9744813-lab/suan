# NovelForge 2.0

> 长篇小说 AI 协同工作台 — 6 个核心 Agent(Chief / Planner / Drafter / Critic / Rewriter / Continuity / MemoryUpdate / Learning) +
> ContextCompiler + DetailGuard + 多层记忆 + 24h Worker 续写器 + Prompt 模板中心 + 模型角色绑定 + SSE 实时事件流。

## 目录

- [架构一览](#架构一览)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [Mock LLM](#mock-llm)
- [下一步](#下一步)

## 架构一览

```
                    ┌─────────────┐
   总编侧栏   ───►  │  ChiefAgent │  ◄── 聊天 / 调度动作
                    └──────┬──────┘
                           │ 调度
   Worker 启动/暂停 ───►  ┌▼──────────┐    ◄── agent_tasks 队列
                         │ Worker    │       (asyncio in-process)
                         └────┬──────┘
                              │ 取下一个任务
                  ┌───────────▼────────────┐
                  │   ChapterPipeline       │
                  │ ┌────────────────────┐  │
                  │ │ ContextCompiler    │  │  设定/记忆/伏笔/角色 → 上下文包
                  │ │ DetailGuard        │  │  硬冲突预检
                  │ │ PlannerAgent       │  │  beat / 场景 / 角色表
                  │ │ DrafterAgent       │  │  正文（稿纸感中文）
                  │ │ DetailGuard 后置   │  │  写后核对
                  │ │ CriticAgent        │  │  加权评分
                  │ │ RewriterAgent×N    │  │  改稿循环(最多 N 轮)
                  │ │ ContinuityAgent    │  │  连续性
                  │ │ MemoryUpdateAgent  │  │  写回记忆
                  │ │ LearningAgent      │  │  复盘
                  │ └────────────────────┘  │
                  └─────────────────────────┘
                              │
                              ▼
                  ┌────────────────────────┐
                  │ PromptEngine + LLMRtr  │  ◄── Prompt 模板中心 + 模型角色绑定
                  └────────────────────────┘
```

详见 `docs/spec.md`（技术规范）和 `docs/ui-ux.md`（UI/UX 规范）。

## 快速开始

### 0. 准备

- Python 3.11（已使用 3.11.9 测试通过）
- Node 20+（已使用 Node 20 测试通过）
- 一个 OpenAI 兼容 LLM（可选，**默认用 mock LLM 跑通全链路**）

### 1. 启动后端

```bash
cd backend
py -3.11 -m pip install -e .
py -3.11 -m app.seed       # 建表 + 种入 10 个 Prompt 模板 + stub Provider + 角色绑定
py -3.11 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

后端启动后访问 <http://127.0.0.1:8000/health> 应返回 `{"ok":true,"data":{"status":"ok","version":"0.1.0"}}`。

API 文档自动生成在 <http://127.0.0.1:8000/docs>。

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

打开 <http://127.0.0.1:5173/>。Vite 会把 `/api/*` 代理到后端 `127.0.0.1:8000`。

### 3. 走一遍

1. 工作台 → 项目页 → "新建项目"
2. 切到「主设定」标签页写入世界观、主角
3. 切到「大纲」标签页，批量加几章
4. 切到「章节」标签页，对第一章点「开始流水线」
5. Worker 自动跑 6 个 Agent，1~2 分钟后打开「章节详情」看「正文 / 版本 / 时间线 / 上下文」四个标签

## 项目结构

```
wudi8633/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI 入口（lifespan 启动 + 路由挂载）
│   │   ├── seed.py                # 默认 Prompt + Provider + 角色绑定 seed
│   │   ├── core/                  # config / database / errors / events / security
│   │   ├── models/                # SQLAlchemy ORM（11 张表）
│   │   ├── schemas/               # Pydantic v2 schemas
│   │   ├── services/              # LLM client + router, prompt engine, context compiler,
│   │   │                          # detail guard, memory, learning
│   │   ├── agents/                # 6 个核心 Agent + base class
│   │   ├── workers/               # 异步 worker + chapter pipeline
│   │   ├── routers/               # 9 个 API 路由分组
│   │   └── prompts/default/       # 10 个默认 Prompt 模板（中文）
│   ├── pyproject.toml
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── main.tsx               # React 入口
│   │   ├── App.tsx                # 路由
│   │   ├── styles/global.css      # 暗色编辑室主题（CSS 变量）
│   │   ├── types/                 # 与后端 schema 对齐的 TypeScript 类型
│   │   ├── api/                   # 强类型 fetch 客户端
│   │   ├── stores/                # Zustand: project / worker / chief / event
│   │   ├── hooks/                 # useSSE（自动重连）
│   │   ├── components/            # AppShell(4 区) + ChiefAgentPanel
│   │   └── pages/                 # 10 个页面
│   ├── vite.config.ts             # /api → 8000 代理
│   └── package.json
└── docs/
    ├── spec.md                    # 技术规范（v2）
    └── ui-ux.md                   # UI/UX 规范（v2）
```

## Mock LLM

为了让系统在没有 API Key 的情况下也能跑全链路,`app/services/llm/client.py` 内置了一个
mock LLM:

- 当 Provider 的 `base_url` 以 `mock://` 开头时启用
- 6 个 Agent 都有预制的占位回复(剧情走向、Critic 评分、记忆增量等)
- 入口的 stub Provider 在 seed 时已自动建好,所有角色绑定都指向它
- 切到「模型」页新建一个真实 OpenAI 兼容 Provider,把角色绑过去即可走真实模型

## 下一步

- [ ] Memory Agent(角色、硬事实、伏笔)的增量化写入
- [ ] 拆书 / 行为模式卡(Study / BehaviorPattern Agent)UI
- [ ] 知识图谱(GraphRAG)页
- [ ] 讨论室(DiscussionRoom)多人轮换
- [ ] Frontend:章节对比视图(左稿纸 / 右建议)
- [ ] Docker compose(PostgreSQL + 后端 + 前端 nginx)
- [ ] 多用户与权限
