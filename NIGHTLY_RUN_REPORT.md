# NIGHTLY_RUN_REPORT.md

## 运行摘要

- 运行状态：完成
- 技术栈：FastAPI / SQLAlchemy / SQLite，React / Vite 前端
- 模型：deepseek-v4-flash-free
- 源书：诡秘之主.txt
- 500 章目录：500/500
- 已生成章节：46/50
- 已评审章节：46/50
- 已返工章节：33
- 记忆更新：46/50

## 拆书结果

- 拆分章节：120
- 人物卡：24
- 关系边：8
- 技巧/桥段：5/4

## 错误与阻塞

- chapter_11：RuntimeError: 第 11 章返工后仍过短：2 字
- chapter_26：RuntimeError: 第 26 章正文过短：444 字
- chapter_27：RuntimeError: 第 27 章正文过短：288 字
- chapter_48：RuntimeError: 第 48 章返工后仍过短：2 字

## 下一步建议

- 若要 full 模式，保持相同命令并提高 `--chapter-limit` 或去掉 smoke 限制。
- 如果 API 限流，使用当前 `runtime/nightly/progress.json` 续跑。
