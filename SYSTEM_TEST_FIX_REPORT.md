# SYSTEM_TEST_FIX_REPORT.md

## 项目诊断与修复

- 运行状态：完成
- 技术栈：FastAPI / SQLAlchemy / SQLite，React / Vite 前端
- 模型：deepseek-v4-flash-free
- 源书：诡秘之主.txt
- 500 章目录：500/500
- 已生成章节：46/50
- 已评审章节：46/50
- 已返工章节：33
- 记忆更新：46/50

## 执行过的命令

- `拆书：分章`：通过；产出 120 段
- `拆书：500章目录`：通过；卷数 10, 章数 500
- `章节 1`：通过；score=0, rewritten=True, chars=5746
- `章节 2`：通过；score=0, rewritten=True, chars=4408
- `章节 3`：通过；score=75, rewritten=True, chars=3465
- `章节 4`：通过；score=0, rewritten=True, chars=5457
- `章节 5`：通过；score=0, rewritten=True, chars=5111
- `章节 6`：通过；score=92, rewritten=False, chars=2780
- `章节 7`：通过；score=0, rewritten=True, chars=1588
- `章节 8`：通过；score=95, rewritten=False, chars=3156
- `章节 9`：通过；score=92, rewritten=False, chars=3693
- `章节 10`：通过；score=0, rewritten=True, chars=3346
- `章节 12`：通过；score=0, rewritten=True, chars=2046
- `章节 13`：通过；score=95, rewritten=True, chars=4716
- `章节 14`：通过；score=92, rewritten=True, chars=5501
- `章节 15`：通过；score=0, rewritten=True, chars=4774
- `章节 16`：通过；score=92, rewritten=False, chars=2801
- `章节 17`：通过；score=92, rewritten=False, chars=1513
- `章节 18`：通过；score=0, rewritten=True, chars=4361
- `章节 19`：通过；score=95, rewritten=True, chars=2230
- `章节 20`：通过；score=95, rewritten=True, chars=2209
- `章节 21`：通过；score=95, rewritten=False, chars=2534
- `章节 22`：通过；score=0, rewritten=True, chars=3097
- `章节 23`：通过；score=90, rewritten=False, chars=2218
- `章节 24`：通过；score=0, rewritten=True, chars=3693
- `章节 25`：通过；score=95, rewritten=True, chars=2747
- `章节 28`：通过；score=0, rewritten=True, chars=4818
- `章节 29`：通过；score=93, rewritten=False, chars=2890
- `章节 30`：通过；score=60, rewritten=True, chars=5682
- `章节 31`：通过；score=93, rewritten=True, chars=2840
- `章节 32`：通过；score=0, rewritten=True, chars=3211
- `章节 33`：通过；score=92, rewritten=False, chars=2451
- `章节 34`：通过；score=35, rewritten=True, chars=3122
- `章节 35`：通过；score=95, rewritten=True, chars=2182
- `章节 36`：通过；score=95, rewritten=False, chars=2838
- `章节 37`：通过；score=95, rewritten=False, chars=2710
- `章节 38`：通过；score=92, rewritten=True, chars=1980
- `章节 39`：通过；score=0, rewritten=True, chars=2973
- `章节 40`：通过；score=95, rewritten=True, chars=2550
- `章节 41`：通过；score=95, rewritten=False, chars=2262
- `章节 42`：通过；score=20, rewritten=True, chars=4544
- `章节 43`：通过；score=95, rewritten=False, chars=4871
- `章节 44`：通过；score=95, rewritten=True, chars=2090
- `章节 45`：通过；score=0, rewritten=True, chars=5311
- `章节 46`：通过；score=95, rewritten=True, chars=2674
- `章节 47`：通过；score=0, rewritten=True, chars=2532
- `章节 49`：通过；score=0, rewritten=True, chars=3247
- `章节 50`：通过；score=92, rewritten=True, chars=5757

## 摘要

- 执行步骤数：48
- 章节级步骤数：46

## 初始失败项

- 前端 `npm run build` 初始失败：未安装依赖导致 `tsc` 不存在。
- 后端全量测试初始失败：删除 Provider 后 `model_call_events.provider_id` 未置空。

## 已修复问题

- 显式置空 Provider 相关调用事件的 `provider_id`，保留审计事件并兼容旧 SQLite 库。
- 安装前端依赖后构建通过。

## 未修复/阻塞

- chapter_11：RuntimeError: 第 11 章返工后仍过短：2 字
- chapter_26：RuntimeError: 第 26 章正文过短：444 字
- chapter_27：RuntimeError: 第 27 章正文过短：288 字
- chapter_48：RuntimeError: 第 48 章返工后仍过短：2 字
