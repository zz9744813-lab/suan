# NovelForge 2.0 DeepStudy 真正大模型拆书重建 Plan

> 目标：把当前 DeepStudy 从“流程跑完但内容假完成”的半成品，升级为真正调用 API 大模型、能抽取人物/事件/关系/伏笔/行为模式/写作技巧，并能反哺写作系统的拆书引擎。
>
> 核心原则：**拆书完成 = 大模型真实分析完成 + 产物入库 + 有证据链 + 有模型调用记录 + 可追溯成本**。
>
> 禁止未实现阶段自动标记完成。

---

## 0. 当前问题判断

当前自动 DeepStudy 主流程大致是：

```txt
上传 / 粘贴正文
→ 解析文本
→ 自动分章
→ 创建 DeepStudy Run
→ Worker 推进 DAG
→ UI 显示拆解进度
```

但核心问题是：

```txt
很多 stage 没有真实 handler
没有 handler 的 stage 被标记为 completed
已有 handler 主要是规则 / 正则
没有真正大