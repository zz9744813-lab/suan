# 后端风格/反模式 (Phase 2.5)

判定阈值：
- 函数/方法 > 100 行 → 潜在 god function
- 函数/方法 > 200 行 → 严重 god function（建议拆分）
- 类 > 300 行 → 潜在 god class
- 类 > 600 行 → 严重 god class

扫描: 858 个函数, 415 个类

## 1. Top 20 最长函数

| 排名 | 路径 | 行号 | 函数名 | 长度 | 等级 |
|----:|------|----:|--------|----:|------|
| 1 | `backend/app/seed.py` | 123 | `seed` | 578 | 🔴 严重 |
| 2 | `backend/app/workers/pipeline.py` | 158 | `run` | 518 | 🔴 严重 |
| 3 | `backend/app/routers/graph.py` | 225 | `materialise_from_study` | 262 | 🔴 严重 |
| 4 | `backend/app/services/review/agent_role_runner.py` | 93 | `run` | 244 | 🔴 严重 |
| 5 | `backend/app/routers/tasks.py` | 299 | `task_diagnosis` | 243 | 🔴 严重 |
| 6 | `backend/app/routers/study.py` | 1228 | `_bulk_process_chapter` | 218 | 🔴 严重 |
| 7 | `backend/app/routers/study.py` | 1922 | `enrich_relationships` | 199 | 🟡 中 |
| 8 | `backend/app/services/review/comment_triage_service.py` | 107 | `run_for_chapter` | 197 | 🟡 中 |
| 9 | `backend/app/routers/study.py` | 1527 | `extract_behaviors` | 184 | 🟡 中 |
| 10 | `backend/app/services/model_selector.py` | 287 | `_score_all_candidates` | 183 | 🟡 中 |
| 11 | `backend/app/services/prompt_auto_binder.py` | 58 | `auto_fill_for_agent_genre` | 176 | 🟡 中 |
| 12 | `backend/app/routers/discussion.py` | 232 | `run_discussion` | 168 | 🟡 中 |
| 13 | `backend/app/routers/search.py` | 105 | `search` | 164 | 🟡 中 |
| 14 | `backend/app/workers/worker.py` | 637 | `_run_chapter_pipeline` | 162 | 🟡 中 |
| 15 | `backend/app/routers/reviews.py` | 1213 | `get_auto_flow_status` | 161 | 🟡 中 |
| 16 | `backend/app/services/llm/router.py` | 243 | `_try_fallback` | 160 | 🟡 中 |
| 17 | `backend/app/core/database.py` | 69 | `init_db` | 157 | 🟡 中 |
| 18 | `backend/app/routers/study.py` | 823 | `study_chapter` | 152 | 🟡 中 |
| 19 | `backend/app/services/context_compiler.py` | 44 | `compile` | 150 | 🟡 中 |
| 20 | `backend/app/services/llm/client.py` | 493 | `_do_chat_stream` | 144 | 🟡 中 |

## 2. 严重 god function（> 200 行）

- `backend/app/seed.py:123` —— `seed` (*578 行*)
- `backend/app/workers/pipeline.py:158` —— `run` (*518 行*)
- `backend/app/routers/graph.py:225` —— `materialise_from_study` (*262 行*)
- `backend/app/services/review/agent_role_runner.py:93` —— `run` (*244 行*)
- `backend/app/routers/tasks.py:299` —— `task_diagnosis` (*243 行*)
- `backend/app/routers/study.py:1228` —— `_bulk_process_chapter` (*218 行*)

## 3. 较长函数（100-200 行）

- `backend/app/routers/study.py:1922` —— `enrich_relationships` (*199 行*)
- `backend/app/services/review/comment_triage_service.py:107` —— `run_for_chapter` (*197 行*)
- `backend/app/routers/study.py:1527` —— `extract_behaviors` (*184 行*)
- `backend/app/services/model_selector.py:287` —— `_score_all_candidates` (*183 行*)
- `backend/app/services/prompt_auto_binder.py:58` —— `auto_fill_for_agent_genre` (*176 行*)
- `backend/app/routers/discussion.py:232` —— `run_discussion` (*168 行*)
- `backend/app/routers/search.py:105` —— `search` (*164 行*)
- `backend/app/workers/worker.py:637` —— `_run_chapter_pipeline` (*162 行*)
- `backend/app/routers/reviews.py:1213` —— `get_auto_flow_status` (*161 行*)
- `backend/app/services/llm/router.py:243` —— `_try_fallback` (*160 行*)
- `backend/app/core/database.py:69` —— `init_db` (*157 行*)
- `backend/app/routers/study.py:823` —— `study_chapter` (*152 行*)
- `backend/app/services/context_compiler.py:44` —— `compile` (*150 行*)
- `backend/app/services/llm/client.py:493` —— `_do_chat_stream` (*144 行*)
- `backend/app/services/review/reader_review_service.py:103` —— `run_for_chapter` (*144 行*)
- `backend/app/routers/deepstudy.py:81` —— `list_library` (*138 行*)
- `backend/app/routers/models.py:304` —— `health_check_provider` (*135 行*)
- `backend/app/routers/study.py:2127` —— `apply_relationship_suggestions` (*134 行*)
- `backend/app/routers/study.py:1784` —— `list_relationship_suggestions` (*129 行*)
- `backend/app/routers/chief_agent.py:72` —— `chat` (*126 行*)
- `backend/app/routers/deepstudy.py:463` —— `get_knowledge_graph` (*123 行*)
- `backend/app/services/review/reader_review_service.py:391` —— `_run_one_reader` (*118 行*)
- `backend/app/routers/reviews.py:938` —— `auto_create_review` (*114 行*)
- `backend/app/routers/study.py:237` —— `upload_materials_batch` (*114 行*)
- `backend/app/services/review/reader_review_service.py:278` —— `_build_inputs` (*112 行*)
- `backend/app/services/llm/router.py:131` —— `chat` (*111 行*)
- `backend/app/routers/agent_roles.py:71` —— `get_agent_role_matrix` (*110 行*)
- `backend/app/agents/discussion_orchestrator.py:134` —— `run_thread` (*107 行*)
- `backend/app/routers/study.py:1014` —— `study_bulk` (*107 行*)
- `backend/app/services/review/comment_discussion_runner.py:68` —— `run_for_task` (*104 行*)
- `backend/app/services/agent_run_recorder.py:27` —— `get_summary` (*102 行*)
- `backend/app/agents/base.py:72` —— `run` (*101 行*)

## 4. Top 10 最长类

| 排名 | 路径 | 行号 | 类名 | 长度 | 等级 |
|----:|------|----:|------|----:|------|
| 1 | `backend/app/workers/worker.py` | 52 | `WorkerController` | 835 | 🔴 严重 |
| 2 | `backend/app/workers/pipeline.py` | 146 | `ChapterPipeline` | 678 | 🔴 严重 |
| 3 | `backend/app/services/agent_memory_service.py` | 76 | `AgentMemoryService` | 521 | 🟡 中 |
| 4 | `backend/app/services/llm/client.py` | 375 | `LLMClient` | 501 | 🟡 中 |
| 5 | `backend/app/services/review/reader_review_service.py` | 99 | `ReaderReviewService` | 420 | 🟡 中 |
| 6 | `backend/app/services/review/comment_triage_service.py` | 98 | `CommentTriageService` | 376 | 🟡 中 |
| 7 | `backend/app/services/llm/router.py` | 51 | `LLMRouter` | 352 | 🟡 中 |
| 8 | `backend/app/services/model_selector.py` | 167 | `ModelSelectorService` | 331 | 🟡 中 |
| 9 | `backend/app/agents/discussion_orchestrator.py` | 131 | `DiscussionOrchestrator` | 296 | 🟢 |
| 10 | `backend/app/services/model_call_recorder.py` | 33 | `ModelCallRecorder` | 286 | 🟢 |

## 5. 严重 god class（> 600 行）

- `backend/app/workers/worker.py:52` —— `WorkerController` (*835 行*)
- `backend/app/workers/pipeline.py:146` —— `ChapterPipeline` (*678 行*)

## 6. 统计汇总

| 类别 | 数量 |
|------|----:|
| 总函数 | 858 |
| 总类 | 415 |
| > 200 行函数 | 6 |
| 100-200 行函数 | 32 |
| > 600 行类 | 2 |
| 300-600 行类 | 6 |
