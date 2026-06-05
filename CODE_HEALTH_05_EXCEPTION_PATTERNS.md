# 后端异常处理模式扫描 (Phase 2.3)

扫描范围: `backend/app/`  
`try:` 语句: 143 处  
`except` 子句总数: **136**

## 1. 概览

| 类别 | 数量 |
|------|----:|
| 裸 `except:` | **0** |
| 宽泛 `except Exception/BaseException` | **70** |
| 其中疑似静默吞掉（body 无 raise/return/logger） | **27** |

✅ **无裸 `except:` 语句** —— 全是具名异常类，习惯良好。
## 2. 宽泛 except 清单（按文件聚合）

| 文件 | 处数 | 静默数 |
|------|----:|------:|
| `backend/app/routers/study.py` | 9 | 6 |
| `backend/app/workers/worker.py` | 9 | 2 |
| `backend/app/agents/discussion_orchestrator.py` | 5 | 3 |
| `backend/app/routers/discussion.py` | 4 | 3 |
| `backend/app/routers/models.py` | 4 | 0 |
| `backend/app/services/llm/router.py` | 4 | 2 |
| `backend/app/services/provider_health.py` | 3 | 1 |
| `backend/app/services/review/comment_triage_service.py` | 3 | 0 |
| `backend/app/core/database.py` | 2 | 2 |
| `backend/app/routers/agent_roles.py` | 2 | 1 |
| `backend/app/services/deepstudy/coordinator.py` | 2 | 2 |
| `backend/app/workers/deepstudy_worker.py` | 2 | 0 |
| `backend/app/workers/discussion_recycle_worker.py` | 2 | 0 |
| `backend/app/agents/base.py` | 1 | 1 |
| `backend/app/routers/chief_agent.py` | 1 | 1 |
| `backend/app/routers/reviews.py` | 1 | 0 |
| `backend/app/services/audit_service.py` | 1 | 0 |
| `backend/app/services/deepstudy/event_bus.py` | 1 | 1 |
| `backend/app/services/prompt_auto_binder.py` | 1 | 0 |
| `backend/app/services/prompt_engine.py` | 1 | 0 |
| `backend/app/services/review/reader_review_service.py` | 1 | 0 |
| `backend/app/tests/test_deepstudy_r25.py` | 1 | 0 |
| `backend/app/tests/test_graph_interaction_r23.py` | 1 | 0 |
| `backend/app/tests/test_graph_materialise_extended.py` | 1 | 0 |
| `backend/app/tests/test_llm_router_fallback.py` | 1 | 1 |
| `backend/app/tests/test_router_r21.py` | 1 | 1 |
| `backend/app/tests/test_study_behavior_extract.py` | 1 | 0 |
| `backend/app/tests/test_study_chapterize.py` | 1 | 0 |
| `backend/app/tests/test_study_foreshadows_endpoint.py` | 1 | 0 |
| `backend/app/tests/test_study_relationship_enrich_r24.py` | 1 | 0 |
| `backend/app/tests/test_study_relationships.py` | 1 | 0 |
| `backend/app/workers/discussion_worker.py` | 1 | 0 |

## 3. 疑似静默 except（body 无 raise/log/return）

⚠️ 以下 `except` 块的 body 看不到任何日志记录或重新抛出，异常可能被吞掉。

- `backend/app/agents/base.py:110` —— `except Exception as exc as :`
  - body: `step.status = "failed" | step.error_message = str(exc) | step.finished_at = datetime.utcnow() | await ctx.db.flush() | raise`
- `backend/app/agents/discussion_orchestrator.py:221` —— `except Exception as :`
  - body: `pass  # Skill 草案创建失败不影响主流程`
- `backend/app/agents/discussion_orchestrator.py:234` —— `except Exception as exc as :`
  - body: `thread.status = "failed" | thread.updated_at = datetime.utcnow() | try: | await db.commit() | except Exception: | pass`
- `backend/app/agents/discussion_orchestrator.py:239` —— `except Exception as :`
  - body: `pass`
- `backend/app/core/database.py:48` —— `except Exception as :`
  - body: `await session.rollback() | raise`
- `backend/app/core/database.py:62` —— `except Exception as :`
  - body: `await session.rollback() | raise`
- `backend/app/routers/agent_roles.py:497` —— `except Exception as exc as :`
  - body: `failed += 1 | items.append(AutoConfigureItem( | agent_role_key=role.key, | selection_mode="auto", | provider=None, | model=None, | score=None, | reason=f"失败: {exc}", | ))`
- `backend/app/routers/chief_agent.py:147` —— `except Exception as exc as :`
  - body: `# fall back to a heuristic reply so the UI never goes silent | fallback = { | "reply": ( | f"收到消息「{body.message[:40]}」。当前 LLM 不可用（{exc}），" | "请先在「模型配置」页配置一个可用的 Provider。" | ), | "actions": [ | { | "ac`
- `backend/app/routers/discussion.py:215` —— `except Exception as :`
  - body: `pass`
- `backend/app/routers/discussion.py:341` —— `except Exception as exc as :`
  - body: `synth_elapsed = int((time.time() - t0) * 1000) if 't0' in locals() else 0 | synth_row_kwargs = { | "agent_name": "ChiefAgent", "role_label": "总编", | "kind": "synthesis", | "content": "", "parsed": Non`
- `backend/app/routers/discussion.py:354` —— `except Exception as :`
  - body: `pass`
- `backend/app/routers/study.py:187` —— `except Exception as :`
  - body: `num_int = i + 1`
- `backend/app/routers/study.py:336` —— `except Exception as exc as :`
  - body: `entry["chapterize_error"] = str(exc)`
- `backend/app/routers/study.py:344` —— `except Exception as exc as :`
  - body: `results.append({ | "ok": False, | "filename": f.filename, | "error": f"{exc.__class__.__name__}: {exc}".strip(), | })`
- `backend/app/routers/study.py:501` —— `except Exception as :`
  - body: `text = ""`
- `backend/app/routers/study.py:1646` —— `except Exception as exc as :`
  - body: `study_task.status = "failed" | study_task.error = str(exc) | study_task.finished_at = datetime.utcnow() | await db.flush() | raise`
- `backend/app/routers/study.py:2084` —— `except Exception as :`
  - body: `# LLM 调用本身失败 → 跳过, 但仍然 emit 一条 item 维持 | # 候选对完整 (用户在前端看到 "抽取失败" 仍能看 co-occurrence) | skipped += 1`
- `backend/app/services/deepstudy/coordinator.py:176` —— `except Exception as :`
  - body: `# Materialisation failure should not block stage advancement. | pass`
- `backend/app/services/deepstudy/coordinator.py:216` —— `except Exception as e as :`
  - body: `run.status = "failed" | run.error = str(e) | run.finished_at = datetime.now(timezone.utc) | await deepstudy_event_bus.stage_completed( | material_id=material_id, | run_id=run.id, | stage_key="run_fail`
- `backend/app/services/deepstudy/event_bus.py:63` —— `except Exception as :`
  - body: `# Swallow per-listener errors so one bad subscriber | # doesn't break the entire pipeline. | pass`
- `backend/app/services/llm/router.py:381` —— `except Exception as exc2 as :`
  - body: `failed_set.add((cand.provider_id, cand.model_name)) | if recorder and event: | failure_type2 = classify_llm_exception(exc2) | await recorder.record_failure(db, event, failure_type2, str(exc2)[:2000]) `
- `backend/app/services/llm/router.py:393` —— `except Exception as :`
  - body: `pass`
- `backend/app/services/provider_health.py:96` —— `except Exception as exc as :`
  - body: `scores["chat_short"] = 0.0 | details["short_chat_error"] = str(exc)[:200]`
- `backend/app/tests/test_llm_router_fallback.py:131` —— `except Exception as :`
  - body: `pass  # fallback 可能也会失败, 测试重点在调用次数`
- `backend/app/tests/test_router_r21.py:137` —— `except HTTPException as exc as :`
  - body: `assert exc.status_code == 400 | assert "StudyAgent" in str(exc.detail) or "Provider" in str(exc.detail)`
- `backend/app/workers/worker.py:402` —— `except Exception as exc as :`
  - body: `err_text = str(exc) | async with session_scope() as db: | t = await db.get(AgentTask, target_task_id) | t.status = "failed" | t.error = err_text | t.finished_at = datetime.utcnow() | ws3 = await self.`
- `backend/app/workers/worker.py:631` —— `except Exception as exc as :`
  - body: `err_text = str(exc) | await self._mark_task_failed(target_task_id, err_text)`

## 4. 综合判断

- ✅ 无裸 `except:`
- 🟡 存在 27 处疑似静默异常处理（body 无 raise/log），建议人工逐一复核
- 🟡 `except Exception` 数量较多（70 处），但分散在 33 个文件，多为 LLM 路由/重试/HTTP 容错的合理场景