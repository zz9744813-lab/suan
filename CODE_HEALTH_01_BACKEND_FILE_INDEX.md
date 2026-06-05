# 后端文件清单 (backend/app/)

生成时间: 2026-06-05  
根目录: `backend/app/`  
文件总数: **161**

## 1. 子包聚合统计（按目录）

| 子包 | 文件数 | 总字节 | 总行数 | 代码行 |
|------|-------:|-------:|------:|------:|
| `__init__.py` | 1 | 60 | 2 | 2 |
| `agents` | 12 | 47,651 | 1,286 | 1,008 |
| `core` | 6 | 19,895 | 495 | 351 |
| `main.py` | 1 | 3,193 | 121 | 102 |
| `models` | 21 | 167,885 | 3,632 | 2,542 |
| `prompts` | 3 | 59,416 | 1,127 | 1,113 |
| `routers` | 26 | 456,546 | 11,842 | 9,725 |
| `schemas` | 19 | 126,514 | 4,091 | 3,085 |
| `seed.py` | 1 | 38,320 | 705 | 601 |
| `services` | 44 | 404,489 | 10,857 | 8,901 |
| `tests` | 21 | 166,978 | 4,378 | 3,436 |
| `workers` | 6 | 80,836 | 1,948 | 1,673 |
| **合计** | **161** | **1,571,783** | **40,484** | **32,539** |

## 2. Top 20 最大文件（按字节）

| 排名 | 路径 | 字节 | 总行 | 代码行 | 注释 | 空行 |
|----:|------|-----:|----:|-----:|----:|----:|
| 1 | `backend/app/routers/study.py` | 95,669 | 2,388 | 1,974 | 245 | 169 |
| 2 | `backend/app/prompts/default/library.py` | 59,250 | 1,122 | 1,109 | 7 | 6 |
| 3 | `backend/app/routers/reviews.py` | 49,289 | 1,373 | 1,131 | 117 | 125 |
| 4 | `backend/app/services/llm/client.py` | 41,791 | 1,002 | 800 | 108 | 94 |
| 5 | `backend/app/routers/models.py` | 40,959 | 1,005 | 841 | 80 | 84 |
| 6 | `backend/app/workers/worker.py` | 40,072 | 896 | 773 | 57 | 66 |
| 7 | `backend/app/services/agent_memory_service.py` | 39,335 | 1,045 | 878 | 40 | 127 |
| 8 | `backend/app/seed.py` | 38,320 | 705 | 601 | 79 | 25 |
| 9 | `backend/app/workers/pipeline.py` | 33,497 | 823 | 723 | 54 | 46 |
| 10 | `backend/app/routers/deepstudy.py` | 29,256 | 774 | 666 | 39 | 69 |
| 11 | `backend/app/routers/project_memory.py` | 26,551 | 602 | 477 | 70 | 55 |
| 12 | `backend/app/models/deepstudy.py` | 23,896 | 473 | 319 | 99 | 55 |
| 13 | `backend/app/routers/tasks.py` | 21,739 | 529 | 435 | 57 | 37 |
| 14 | `backend/app/services/model_selector.py` | 20,240 | 509 | 398 | 35 | 76 |
| 15 | `backend/app/routers/agent_roles.py` | 19,652 | 511 | 426 | 26 | 59 |
| 16 | `backend/app/services/review/reader_review_service.py` | 19,556 | 528 | 439 | 33 | 56 |
| 17 | `backend/app/services/review/comment_triage_service.py` | 19,411 | 523 | 447 | 21 | 55 |
| 18 | `backend/app/routers/discussion_trace.py` | 18,442 | 511 | 387 | 44 | 80 |
| 19 | `backend/app/routers/graph.py` | 18,317 | 486 | 406 | 37 | 43 |
| 20 | `backend/app/services/llm/router.py` | 17,703 | 413 | 350 | 23 | 40 |

## 3. 完整文件清单

| 路径 | 字节 | 总行 | 代码 | 注释 | 空行 |
|------|-----:|----:|---:|----:|----:|
| `backend/app/__init__.py` | 60 | 2 | 2 | 0 | 0 |
| `backend/app/agents/__init__.py` | 747 | 24 | 23 | 0 | 1 |
| `backend/app/agents/base.py` | 13,850 | 351 | 267 | 52 | 32 |
| `backend/app/agents/chief.py` | 1,797 | 62 | 54 | 0 | 8 |
| `backend/app/agents/continuity.py` | 1,873 | 46 | 31 | 8 | 7 |
| `backend/app/agents/critic.py` | 1,889 | 51 | 34 | 11 | 6 |
| `backend/app/agents/discussion_orchestrator.py` | 14,893 | 426 | 361 | 13 | 52 |
| `backend/app/agents/drafter.py` | 366 | 14 | 11 | 0 | 3 |
| `backend/app/agents/learner.py` | 351 | 13 | 10 | 0 | 3 |
| `backend/app/agents/memory_updater.py` | 3,367 | 82 | 53 | 21 | 8 |
| `backend/app/agents/planner.py` | 622 | 17 | 10 | 4 | 3 |
| `backend/app/agents/rewriter.py` | 346 | 13 | 10 | 0 | 3 |
| `backend/app/agents/study.py` | 7,550 | 187 | 144 | 17 | 26 |
| `backend/app/core/__init__.py` | 0 | 1 | 0 | 0 | 0 |
| `backend/app/core/config.py` | 2,560 | 79 | 43 | 18 | 18 |
| `backend/app/core/database.py` | 11,411 | 227 | 159 | 47 | 21 |
| `backend/app/core/errors.py` | 1,915 | 68 | 55 | 0 | 13 |
| `backend/app/core/events.py` | 3,367 | 102 | 80 | 3 | 19 |
| `backend/app/core/security.py` | 642 | 18 | 14 | 0 | 4 |
| `backend/app/main.py` | 3,193 | 121 | 102 | 3 | 16 |
| `backend/app/models/__init__.py` | 4,927 | 189 | 177 | 10 | 2 |
| `backend/app/models/agent_memory.py` | 13,714 | 325 | 236 | 34 | 55 |
| `backend/app/models/agent_role.py` | 11,601 | 225 | 160 | 34 | 31 |
| `backend/app/models/audit_log.py` | 3,142 | 84 | 60 | 9 | 15 |
| `backend/app/models/behavior_card.py` | 8,720 | 186 | 124 | 23 | 39 |
| `backend/app/models/chief_agent.py` | 1,807 | 40 | 29 | 0 | 11 |
| `backend/app/models/comment_review.py` | 13,712 | 356 | 241 | 44 | 71 |
| `backend/app/models/deepstudy.py` | 23,896 | 473 | 319 | 99 | 55 |
| `backend/app/models/discussion.py` | 3,095 | 67 | 49 | 5 | 13 |
| `backend/app/models/discussion_trace.py` | 11,326 | 247 | 153 | 30 | 64 |
| `backend/app/models/genre_prompt_map.py` | 4,040 | 87 | 62 | 9 | 16 |
| `backend/app/models/memory.py` | 5,332 | 101 | 72 | 6 | 23 |
| `backend/app/models/memory_v2.py` | 14,795 | 290 | 196 | 57 | 37 |
| `backend/app/models/model_call_event.py` | 4,539 | 100 | 60 | 18 | 22 |
| `backend/app/models/model_provider.py` | 4,535 | 84 | 58 | 9 | 17 |
| `backend/app/models/model_runtime.py` | 2,283 | 57 | 39 | 2 | 16 |
| `backend/app/models/project.py` | 6,134 | 120 | 86 | 8 | 26 |
| `backend/app/models/prompt.py` | 2,575 | 51 | 40 | 0 | 11 |
| `backend/app/models/prompt_auto_fill.py` | 5,446 | 120 | 98 | 0 | 22 |
| `backend/app/models/study.py` | 14,431 | 292 | 181 | 66 | 45 |
| `backend/app/models/task.py` | 7,835 | 138 | 102 | 8 | 28 |
| `backend/app/prompts/__init__.py` | 38 | 1 | 1 | 0 | 0 |
| `backend/app/prompts/default/__init__.py` | 128 | 4 | 3 | 0 | 1 |
| `backend/app/prompts/default/library.py` | 59,250 | 1,122 | 1,109 | 7 | 6 |
| `backend/app/routers/__init__.py` | 57 | 1 | 1 | 0 | 0 |
| `backend/app/routers/agent_memory.py` | 9,495 | 254 | 190 | 20 | 44 |
| `backend/app/routers/agent_roles.py` | 19,652 | 511 | 426 | 26 | 59 |
| `backend/app/routers/audit.py` | 4,729 | 137 | 106 | 12 | 19 |
| `backend/app/routers/behavior.py` | 4,881 | 127 | 108 | 0 | 19 |
| `backend/app/routers/behavior_card.py` | 5,819 | 144 | 102 | 22 | 20 |
| `backend/app/routers/chapters.py` | 2,498 | 62 | 50 | 0 | 12 |
| `backend/app/routers/chief_agent.py` | 9,821 | 249 | 219 | 9 | 21 |
| `backend/app/routers/deepstudy.py` | 29,256 | 774 | 666 | 39 | 69 |
| `backend/app/routers/discussion.py` | 16,508 | 435 | 381 | 11 | 43 |
| `backend/app/routers/discussion_trace.py` | 18,442 | 511 | 387 | 44 | 80 |
| `backend/app/routers/events.py` | 601 | 24 | 16 | 0 | 8 |
| `backend/app/routers/genre_prompts.py` | 10,139 | 269 | 201 | 28 | 40 |
| `backend/app/routers/graph.py` | 18,317 | 486 | 406 | 37 | 43 |
| `backend/app/routers/memory.py` | 8,329 | 226 | 189 | 4 | 33 |
| `backend/app/routers/model_observability.py` | 17,008 | 418 | 349 | 13 | 56 |
| `backend/app/routers/models.py` | 40,959 | 1,005 | 841 | 80 | 84 |
| `backend/app/routers/project_memory.py` | 26,551 | 602 | 477 | 70 | 55 |
| `backend/app/routers/projects.py` | 11,093 | 301 | 239 | 20 | 42 |
| `backend/app/routers/prompt_matrix.py` | 17,006 | 518 | 425 | 23 | 70 |
| `backend/app/routers/prompts.py` | 6,032 | 162 | 138 | 2 | 22 |
| `backend/app/routers/reviews.py` | 49,289 | 1,373 | 1,131 | 117 | 125 |
| `backend/app/routers/search.py` | 9,850 | 268 | 219 | 18 | 31 |
| `backend/app/routers/study.py` | 95,669 | 2,388 | 1,974 | 245 | 169 |
| `backend/app/routers/tasks.py` | 21,739 | 529 | 435 | 57 | 37 |
| `backend/app/routers/worker.py` | 2,806 | 68 | 49 | 3 | 16 |
| `backend/app/schemas/__init__.py` | 12,337 | 477 | 467 | 9 | 1 |
| `backend/app/schemas/agent_memory.py` | 9,538 | 357 | 262 | 28 | 67 |
| `backend/app/schemas/agent_role.py` | 8,423 | 236 | 172 | 30 | 34 |
| `backend/app/schemas/audit.py` | 1,461 | 48 | 29 | 6 | 13 |
| `backend/app/schemas/behavior_card.py` | 6,516 | 212 | 151 | 27 | 34 |
| `backend/app/schemas/chief_agent.py` | 1,171 | 50 | 38 | 0 | 12 |
| `backend/app/schemas/common.py` | 1,281 | 48 | 30 | 1 | 17 |
| `backend/app/schemas/deepstudy.py` | 8,408 | 250 | 179 | 30 | 41 |
| `backend/app/schemas/discussion_trace.py` | 7,003 | 240 | 176 | 30 | 34 |
| `backend/app/schemas/genre_prompt.py` | 3,021 | 117 | 78 | 13 | 26 |
| `backend/app/schemas/memory.py` | 3,548 | 122 | 94 | 1 | 27 |
| `backend/app/schemas/memory_v2.py` | 9,539 | 273 | 179 | 51 | 43 |
| `backend/app/schemas/model_failover.py` | 4,646 | 154 | 110 | 18 | 26 |
| `backend/app/schemas/model_provider.py` | 10,210 | 276 | 207 | 31 | 38 |
| `backend/app/schemas/project.py` | 4,043 | 155 | 114 | 10 | 31 |
| `backend/app/schemas/prompt.py` | 1,067 | 50 | 40 | 0 | 10 |
| `backend/app/schemas/review.py` | 10,755 | 301 | 226 | 20 | 55 |
| `backend/app/schemas/study.py` | 17,456 | 515 | 366 | 52 | 97 |
| `backend/app/schemas/task.py` | 6,091 | 210 | 167 | 10 | 33 |
| `backend/app/seed.py` | 38,320 | 705 | 601 | 79 | 25 |
| `backend/app/services/__init__.py` | 484 | 22 | 21 | 0 | 1 |
| `backend/app/services/agent_memory_service.py` | 39,335 | 1,045 | 878 | 40 | 127 |
| `backend/app/services/agent_run_recorder.py` | 11,581 | 277 | 242 | 6 | 29 |
| `backend/app/services/audit_service.py` | 5,341 | 193 | 167 | 2 | 24 |
| `backend/app/services/behavior_card_service.py` | 11,580 | 314 | 248 | 35 | 31 |
| `backend/app/services/chapter_queue.py` | 3,938 | 116 | 91 | 7 | 18 |
| `backend/app/services/context_compiler.py` | 10,678 | 285 | 242 | 15 | 28 |
| `backend/app/services/deepstudy/__init__.py` | 1,525 | 52 | 48 | 0 | 4 |
| `backend/app/services/deepstudy/auto_repair.py` | 4,878 | 125 | 91 | 11 | 23 |
| `backend/app/services/deepstudy/behavior_miner.py` | 5,024 | 137 | 102 | 12 | 23 |
| `backend/app/services/deepstudy/coordinator.py` | 9,295 | 228 | 174 | 16 | 38 |
| `backend/app/services/deepstudy/event_bus.py` | 2,989 | 97 | 76 | 3 | 18 |
| `backend/app/services/deepstudy/graph_materializer.py` | 10,595 | 275 | 216 | 23 | 36 |
| `backend/app/services/deepstudy/job_graph.py` | 3,127 | 95 | 78 | 1 | 16 |
| `backend/app/services/deepstudy/knowledge_indexer.py` | 6,555 | 182 | 160 | 2 | 20 |
| `backend/app/services/deepstudy/stage_result_store.py` | 5,645 | 164 | 139 | 3 | 22 |
| `backend/app/services/deepstudy/technique_miner.py` | 4,353 | 120 | 91 | 10 | 19 |
| `backend/app/services/deepstudy/writing_context_sync.py` | 4,845 | 138 | 107 | 9 | 22 |
| `backend/app/services/detail_guard.py` | 4,134 | 107 | 78 | 8 | 21 |
| `backend/app/services/discussion_trace.py` | 12,394 | 347 | 292 | 15 | 40 |
| `backend/app/services/learning.py` | 2,681 | 84 | 72 | 0 | 12 |
| `backend/app/services/llm/__init__.py` | 31 | 1 | 1 | 0 | 0 |
| `backend/app/services/llm/client.py` | 41,791 | 1,002 | 800 | 108 | 94 |
| `backend/app/services/llm/error_classifier.py` | 1,569 | 46 | 35 | 3 | 8 |
| `backend/app/services/llm/pricing.py` | 2,050 | 63 | 45 | 7 | 11 |
| `backend/app/services/llm/router.py` | 17,703 | 413 | 350 | 23 | 40 |
| `backend/app/services/memory.py` | 4,527 | 131 | 108 | 5 | 18 |
| `backend/app/services/model_call_recorder.py` | 11,577 | 318 | 270 | 17 | 31 |
| `backend/app/services/model_capability.py` | 3,981 | 130 | 123 | 3 | 4 |
| `backend/app/services/model_circuit_breaker.py` | 9,423 | 245 | 201 | 15 | 29 |
| `backend/app/services/model_selector.py` | 20,240 | 509 | 398 | 35 | 76 |
| `backend/app/services/pipeline_resume.py` | 9,534 | 254 | 190 | 32 | 32 |
| `backend/app/services/prompt_auto_binder.py` | 11,275 | 300 | 245 | 12 | 43 |
| `backend/app/services/prompt_engine.py` | 8,577 | 231 | 188 | 13 | 30 |
| `backend/app/services/provider_health.py` | 6,011 | 164 | 132 | 11 | 21 |
| `backend/app/services/review/__init__.py` | 5,174 | 144 | 123 | 7 | 14 |
| `backend/app/services/review/agent_role_runner.py` | 12,176 | 346 | 293 | 19 | 34 |
| `backend/app/services/review/comment_cleanup_service.py` | 5,334 | 157 | 119 | 8 | 30 |
| `backend/app/services/review/comment_discussion_runner.py` | 8,965 | 257 | 210 | 12 | 35 |
| `backend/app/services/review/comment_triage_service.py` | 19,411 | 523 | 447 | 21 | 55 |
| `backend/app/services/review/discussion_bridge.py` | 10,985 | 291 | 231 | 23 | 37 |
| `backend/app/services/review/queue_service.py` | 9,470 | 274 | 232 | 10 | 32 |
| `backend/app/services/review/reader_review_service.py` | 19,556 | 528 | 439 | 33 | 56 |
| `backend/app/services/review/weight_service.py` | 4,152 | 127 | 108 | 1 | 18 |
| `backend/app/tests/__init__.py` | 52 | 1 | 0 | 1 | 0 |
| `backend/app/tests/test_agent_run_recorder.py` | 5,665 | 163 | 129 | 4 | 30 |
| `backend/app/tests/test_bulk_limit_r21.py` | 3,232 | 93 | 78 | 0 | 15 |
| `backend/app/tests/test_circuit_breaker.py` | 5,959 | 168 | 142 | 5 | 21 |
| `backend/app/tests/test_deepstudy_r25.py` | 13,320 | 381 | 286 | 31 | 64 |
| `backend/app/tests/test_graph_interaction_r23.py` | 11,084 | 313 | 235 | 18 | 60 |
| `backend/app/tests/test_graph_materialise_extended.py` | 7,185 | 201 | 149 | 18 | 34 |
| `backend/app/tests/test_llm_client_prompt_mode.py` | 3,621 | 94 | 75 | 1 | 18 |
| `backend/app/tests/test_llm_router_fallback.py` | 8,061 | 214 | 180 | 8 | 26 |
| `backend/app/tests/test_model_selector_failover.py` | 9,588 | 270 | 213 | 17 | 40 |
| `backend/app/tests/test_p5_regression.py` | 17,194 | 402 | 285 | 49 | 68 |
| `backend/app/tests/test_prompt_auto_binder.py` | 9,809 | 275 | 215 | 14 | 46 |
| `backend/app/tests/test_provider_health_service.py` | 4,657 | 124 | 98 | 5 | 21 |
| `backend/app/tests/test_router_r21.py` | 8,474 | 206 | 166 | 10 | 30 |
| `backend/app/tests/test_study_batch_upload.py` | 7,130 | 199 | 156 | 15 | 28 |
| `backend/app/tests/test_study_behavior_extract.py` | 5,799 | 157 | 128 | 7 | 22 |
| `backend/app/tests/test_study_chapterize.py` | 8,400 | 178 | 145 | 11 | 22 |
| `backend/app/tests/test_study_foreshadows_endpoint.py` | 8,654 | 221 | 176 | 16 | 29 |
| `backend/app/tests/test_study_relationship_enrich_r24.py` | 13,022 | 334 | 277 | 13 | 44 |
| `backend/app/tests/test_study_relationships.py` | 7,951 | 201 | 163 | 11 | 27 |
| `backend/app/tests/test_worker_retry_delay.py` | 8,121 | 183 | 140 | 14 | 29 |
| `backend/app/workers/__init__.py` | 308 | 10 | 9 | 0 | 1 |
| `backend/app/workers/deepstudy_worker.py` | 1,449 | 48 | 35 | 2 | 11 |
| `backend/app/workers/discussion_recycle_worker.py` | 3,629 | 110 | 87 | 5 | 18 |
| `backend/app/workers/discussion_worker.py` | 1,881 | 61 | 46 | 2 | 13 |
| `backend/app/workers/pipeline.py` | 33,497 | 823 | 723 | 54 | 46 |
| `backend/app/workers/worker.py` | 40,072 | 896 | 773 | 57 | 66 |
