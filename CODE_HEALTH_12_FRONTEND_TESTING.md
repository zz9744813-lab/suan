# 前端测试体系盘点 (Phase 3.4)

## 1. 自动化测试框架

| 框架 | 是否配置 | 证据 |
|------|---------|------|
| **vitest** | ❌ 无 | `**/vitest.config.*` 0 命中 |
| **jest** | ❌ 无 | `**/jest.config.*` 0 命中 |
| **playwright** | ❌ 无 | `**/playwright.config.*` 0 命中 |
| **cypress** | ❌ 无 | `**/cypress.config.*` 0 命中 |
| **@testing-library** | ❌ 无 | `package.json` 中无对应依赖 |

## 2. 测试文件搜索

| 模式 | 命中数 |
|------|------:|
| `src/**/*.test.*` | **0** |
| `src/**/*.spec.*` | **0** |

## 3. package.json 脚本

`package.json` 第 6-10 行：
```json
"scripts": {
  "dev": "vite",
  "build": "tsc -b && vite build",
  "preview": "vite preview"
}
```

- ❌ 无 `"test"` 脚本
- ❌ 无 `"test:unit"` / `"test:e2e"` / `"test:watch"` 脚本

## 4. 结论

🚨 **前端无自动化测试**（完全缺失）。

**当前唯一质量门**：
- `tsc -b --noEmit` —— **已通过**（Phase 2.2 验证 0 错误）
- `vite build` —— 打包时也跑 `tsc -b` 一次

**风险**：
- 任何一次 `git push` 不会触发任何单测
- 重构 API 客户端类型时无回归保护
- 组件交互逻辑（拖拽、表单校验、SSE 订阅）只能靠人工 QA

**建议（P5 push 之后优先做）**：

| 优先级 | 建议 |
|--------|------|
| 🟡 P1 | 引入 **vitest + @testing-library/react**，给 `stores/`（zustand）和 `lib/`（解析、格式化）加单元测试 |
| 🟡 P1 | 引入 **playwright** 跑核心 E2E：登录 → 建项目 → 上传材料 → 触发拆书 → 看图谱 |
| 🟢 P2 | 引入 **MSW (Mock Service Worker)** 拦截 fetch，让组件测试可独立跑 |
| 🟢 P2 | 在 `package.json` 加 `"test"`, `"test:coverage"`, `"test:e2e"` 脚本，CI 中跑 `npm test` |
| 🟢 P2 | 给关键 store（`stores/agentMemory.ts` 等）加 80% 覆盖率门槛 |

## 5. 一个关键细节

前端代码中 grep 到 13 处 `describe(` / `it(` / `test(` / `expect(` 字面量（来自 plan agent 探查），但**全部是 mock 组件名 / 调试菜单字符串**（如 `describe('ReviewDebugMenu')`），**不是测试代码**。

> 这次 grep 由探查阶段确认：在 `frontend/src/` 中无 `*.test.*` / `*.spec.*` 文件，自动化测试框架完全缺失。
