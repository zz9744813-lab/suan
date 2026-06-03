"""Chapter pipeline: Plan -> Draft -> DetailGuard -> Critic -> Rewrite -> Continuity -> Memory -> Learning."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.base import AgentContext
from app.agents.chief import ChiefAgent
from app.agents.continuity import ContinuityAgent
from app.agents.critic import CriticAgent
from app.agents.drafter import DrafterAgent
from app.agents.learner import LearningAgent
from app.agents.memory_updater import MemoryUpdateAgent
from app.agents.planner import PlannerAgent
from app.agents.rewriter import RewriterAgent
from app.core.errors import bad_request
from app.core.events import Event, event_bus
from app.models.project import Chapter, ChapterVersion
from app.models.study import BehaviorPattern
from app.models.task import AgentTask, WorkerPolicy
from app.services.context_compiler import ContextCompiler, get_context_compiler
from app.services.detail_guard import DetailCheckResult, get_detail_guard
from app.services.llm.router import LLMRouter, get_llm_router
from app.services.pipeline_resume import (
    PipelineResumeService,
    ResumedState,
    STEP_ORDER,
)
from app.services.prompt_engine import PromptEngine, get_prompt_engine


async def _query_behavior_patterns_for_chapter(
    db: AsyncSession,
    *,
    characters_present: list[dict[str, Any]],
    top_n: int = 5,
    max_chars: int = 1800,
) -> str:
    """Query the ``behavior_patterns`` table for cards matching the chapter.

    Matching strategy (R15 / Plan A — Plan A.2):
      * Collect every character role + tag string from
        ``characters_present`` (the project's MemoryCharacter roster).
      * Score each ``BehaviorPattern`` by ``len(intersection) * 0.6 +
        confidence`` so a multi-tag match wins over a single very
        confident match.
      * Take the top ``top_n`` and format as a compact text block
        (≤ ``max_chars``) ready to drop into the drafter prompt.

    Returns a human-readable placeholder when the library is empty, the
    project has no characters yet, or no pattern's ``character_tags``
    intersect the project's roster.  Never raises — the drafter step
    must keep running even if the library is broken.
    """
    candidate_tags: set[str] = set()
    for c in characters_present or []:
        role = c.get("role")
        if isinstance(role, str) and role.strip():
            candidate_tags.add(role.strip())
        for t in c.get("tags") or []:
            if isinstance(t, str) and t.strip():
                candidate_tags.add(t.strip())

    if not candidate_tags:
        return (
            "(暂无行为模式：项目里还没有可用的人物标签。"
            "请在「拆书」或「知识库」页面创建人物卡和模式卡。)"
        )

    try:
        rows = (await db.execute(select(BehaviorPattern))).scalars().all()
    except Exception as exc:  # pragma: no cover — defensive
        return f"(行为模式库查询失败：{type(exc).__name__}，已跳过)"

    if not rows:
        return "(项目还没有行为模式库；先在「拆书」或「行为模式」页创建。)"

    scored: list[tuple[float, BehaviorPattern]] = []
    for p in rows:
        p_tags = set(p.character_tags or [])
        if not p_tags:
            continue
        overlap = candidate_tags & p_tags
        if overlap:
            score = len(overlap) * 0.6 + float(p.confidence or 0.0)
            scored.append((score, p))

    if not scored:
        return (
            f"(行为模式库里有 {len(rows)} 条，但没匹配上当前人物标签 "
            f"{sorted(candidate_tags)}。"
            "可多建几条带「主角 / 女主 / 反派」标签的模式。)"
        )

    scored.sort(key=lambda t: t[0], reverse=True)
    top = scored[:top_n]

    parts: list[str] = ["## 行为模式参考（来自 拆书/行为模式 库，按匹配度排序）"]
    for score, p in top:
        lines: list[str] = [f"### 模式: {p.name}（匹配度 {score:.2f}）"]
        if p.character_tags:
            lines.append(f"- 适用人物标签: {', '.join(p.character_tags)}")
        if p.situation_tags:
            lines.append(f"- 适用情境: {', '.join(p.situation_tags)}")
        if p.typical_behavior:
            lines.append(f"- 典型行为: {'；'.join(p.typical_behavior)}")
        if p.dialogue_style:
            lines.append(f"- 对话风格: {'；'.join(p.dialogue_style)}")
        if p.scene_function:
            lines.append(f"- 场景功能: {'；'.join(p.scene_function)}")
        if p.risks:
            lines.append(f"- 风险: {'；'.join(p.risks)}")
        if p.recommended_plot_followup:
            lines.append(f"- 后续推进: {'；'.join(p.recommended_plot_followup)}")
        parts.append("\n".join(lines))

    text = "\n\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…（已截断）"
    return text


@dataclass
class ChapterPipelineResult:
    chapter_id: int
    final_text: str
    final_score: int
    pass_status: str
    rewrite_rounds: int
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    total_duration_ms: int
    hard_conflicts: list[str]
    issues: list[dict[str, Any]]


class ChapterPipeline:
    def __init__(
        self,
        router: LLMRouter | None = None,
        engine: PromptEngine | None = None,
        compiler: ContextCompiler | None = None,
    ) -> None:
        self.router = router or get_llm_router()
        self.engine = engine or get_prompt_engine()
        self.compiler = compiler or get_context_compiler()
        self.detail_guard = get_detail_guard()

    async def run(
        self,
        db: AsyncSession,
        *,
        task: AgentTask,
        chapter: Chapter,
        policy: WorkerPolicy,
    ) -> ChapterPipelineResult:
        t_start = time.perf_counter()
        total_cost = 0.0
        total_in = 0
        total_out = 0
        total_dur = 0

        # 0) Load policy (already passed in) + ensure chapter
        await self._emit(db, task, chapter, "pipeline.started", "开始单章流水线")

        # 0.5) P15 / P0-RETRY-1: read retry_mode and load any
        # previously-succeeded step outputs so we can skip them
        # instead of re-calling the LLM.
        payload = task.payload or {}
        retry_mode = payload.get("retry_mode", "full")
        from_step = payload.get("from_step")
        resume_svc = PipelineResumeService()
        resumed: ResumedState = await resume_svc.load_previous_outputs(
            db, task=task, chapter=chapter,
        )
        if retry_mode != "full" and resumed.last_step is not None:
            await self._emit(
                db, task, chapter,
                "pipeline.retry_resumed",
                f"重试模式 {retry_mode}：从 {resumed.last_step} 之后继续 "
                f"（已 reuse {len(resumed.by_step)} 步）",
                level="info",
            )

        # 1) ContextCompiler (no LLM call, just bundle-building). For
        # retry, we ALWAYS re-run it because ctx_data feeds into every
        # later prompt and depends on the latest character state. The
        # resume algorithm correctly lists it as skippable for
        # documentation purposes but the actual skip happens further
        # down where it matters.
        await self._ensure_not_cancelled(db, task)
        ctx_data = await self.compiler.compile(db, chapter=chapter, policy=policy)
        ctx_inputs = self.compiler.to_prompt_inputs(ctx_data)

        # ---- 2) Planner ----
        await self._ensure_not_cancelled(db, task)
        if resume_svc.should_skip_step(
            "plan",
            mode=retry_mode,
            last_succeeded=resumed.last_step,
            from_step=from_step,
        ) and resumed.plan is not None:
            await resume_svc.record_reused_step(
                db,
                task=task, project_id=chapter.project_id, chapter_id=chapter.id,
                agent_name="PlannerAgent", step_name="plan",
                parsed_output=resumed.plan,
                note=f"retry_mode={retry_mode} 重用上次输出",
            )
            chapter_plan = resumed.plan
        else:
            planner = PlannerAgent(self.router, self.engine)
            planner_result = await planner.run(
                AgentContext(
                    db=db,
                    task=task,
                    project_id=chapter.project_id,
                    chapter_id=chapter.id,
                    inputs=ctx_inputs,
                )
            )
            total_cost += planner_result.cost_usd
            total_in += planner_result.input_tokens
            total_out += planner_result.output_tokens
            total_dur += planner_result.duration_ms
            chapter_plan = planner_result.parsed or {}

        # ---- 3) Drafter ----
        await self._ensure_not_cancelled(db, task)
        if resume_svc.should_skip_step(
            "draft",
            mode=retry_mode,
            last_succeeded=resumed.last_step,
            from_step=from_step,
        ) and resumed.draft_text is not None:
            await resume_svc.record_reused_step(
                db,
                task=task, project_id=chapter.project_id, chapter_id=chapter.id,
                agent_name="DrafterAgent", step_name="draft",
                raw_output=resumed.draft_text,
                note=f"retry_mode={retry_mode} 重用上次草稿",
            )
            draft_text = resumed.draft_text
        else:
            drafter = DrafterAgent(self.router, self.engine)
            # R15 / Plan A.2: query the behavior_patterns library instead of
            # using the hardcoded placeholder. The drafter now sees real
            # reference cards filtered by the project's character roster.
            behavior_patterns_text = await _query_behavior_patterns_for_chapter(
                db,
                characters_present=ctx_data.characters_present,
            )
            # R15 / Plan A.1: hand the drafter an explicit ±200 word window
            # so the 玄幻网文 style hard rule can enforce the target length
            # without the model having to do arithmetic in prose.
            target_wc = int(chapter.target_word_count or 3000)
            min_wc = max(target_wc - 200, 500)
            max_wc = target_wc + 200
            drafter_inputs = {
                "chapter_no": chapter.chapter_no,
                "title": chapter.title,
                "target_word_count": target_wc,
                "min_word_count": min_wc,
                "max_word_count": max_wc,
                "chapter_plan": json.dumps(chapter_plan, ensure_ascii=False, indent=2),
                "memory_context": json.dumps(
                    {
                        "characters_present": ctx_data.characters_present,
                        "character_states": ctx_data.character_states,
                        "active_foreshadows": ctx_data.active_foreshadows,
                        "hard_facts": ctx_data.hard_facts,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "detail_constraints": "\n".join(ctx_data.detail_guard_reminders) or "(无)",
                "behavior_patterns": behavior_patterns_text,
                "style_guide": "稿纸感中文，段间留白，对话短而有情绪。",
                "user_preferences": "(暂无)",
            }
            draft_result = await drafter.run(
                AgentContext(
                    db=db,
                    task=task,
                    project_id=chapter.project_id,
                    chapter_id=chapter.id,
                    inputs=drafter_inputs,
                )
            )
            total_cost += draft_result.cost_usd
            total_in += draft_result.input_tokens
            total_out += draft_result.output_tokens
            total_dur += draft_result.duration_ms
            draft_text = (draft_result.parsed or {}).get("content") or draft_result.raw
            # Drafter has uses_json_output=False but the model sometimes still
            # wraps the prose in {"content": "..."}. Unwrap if present so
            # downstream code sees the raw text, not a JSON envelope.
            if isinstance(draft_text, str) and draft_text.lstrip().startswith("{"):
                try:
                    unwrapped = json.loads(draft_text)
                    if isinstance(unwrapped, dict):
                        for key in ("content", "chapter_content", "text", "body"):
                            v = unwrapped.get(key)
                            if isinstance(v, str) and v.strip():
                                draft_text = v
                                break
                except json.JSONDecodeError:
                    pass

        # 4) DetailGuard post-write
        check = self.detail_guard.post_write_check(ctx_data, draft_text)
        if check.hard_conflicts:
            await self._emit(
                db,
                task,
                chapter,
                "detail_guard.hard_conflict",
                "; ".join(check.hard_conflicts),
                level="warn",
            )

        # ---- 5) Critic ----
        await self._ensure_not_cancelled(db, task)
        critic_report: dict[str, Any]
        final_score: int
        issues: list[dict[str, Any]]
        if resume_svc.should_skip_step(
            "review",
            mode=retry_mode,
            last_succeeded=resumed.last_step,
            from_step=from_step,
        ) and resumed.critic_report is not None:
            # P15 / P0-RETRY-1: continue_with_fallback and
            # from_failed_step can both reuse a successful critic
            # report. critic_only never skips the critic — that's the
            # point of the mode.
            await resume_svc.record_reused_step(
                db,
                task=task, project_id=chapter.project_id, chapter_id=chapter.id,
                agent_name="CriticAgent", step_name="review",
                parsed_output=resumed.critic_report,
                note=f"retry_mode={retry_mode} 重用上次评分",
            )
            critic_report = resumed.critic_report
            final_score = int(critic_report.get("total") or 0)
            issues = critic_report.get("issues") or []
        else:
            critic = CriticAgent(self.router, self.engine)
            critic_inputs = {
                "chapter_no": chapter.chapter_no,
                "title": chapter.title,
                "chapter_plan": json.dumps(chapter_plan, ensure_ascii=False, indent=2),
                "draft_content": draft_text,
                "detail_constraints": "\n".join(ctx_data.detail_guard_reminders) or "(无)",
            }
            critic_result = await critic.run(
                AgentContext(
                    db=db,
                    task=task,
                    project_id=chapter.project_id,
                    chapter_id=chapter.id,
                    inputs=critic_inputs,
                )
            )
            total_cost += critic_result.cost_usd
            total_in += critic_result.input_tokens
            total_out += critic_result.output_tokens
            total_dur += critic_result.duration_ms
            critic_report = critic_result.parsed or {}
            final_score = int(critic_report.get("total") or 0)
            issues = critic_report.get("issues") or []
        await self._save_version(db, chapter, "draft", draft_text, final_score, notes={
            "plan": chapter_plan,
            "critic": critic_report,
            "detail_guard": {
                "hard_conflicts": check.hard_conflicts,
                "soft_warnings": check.soft_warnings,
                "foreshadow_misses": check.foreshadow_misses,
            },
        })

        # 6) Optional Rewrite loop
        await self._ensure_not_cancelled(db, task)
        rewriter = RewriterAgent(self.router, self.engine)
        rewrite_rounds = 0
        # ``current_score`` / ``final_text`` need a defined value even
        # when the rewrite loop is skipped — Continuity / MemoryUpdate
        # / Learning all consume them.
        if resume_svc.should_skip_step(
            "rewrite",
            mode=retry_mode,
            last_succeeded=resumed.last_step,
            from_step=from_step,
        ) and resumed.final_text is not None:
            # P15 / P0-RETRY-1: from_failed_step with from_step after
            # "rewrite" should reuse the last rewrite result. We still
            # go through Continuity / MemoryUpdate / Learning.
            await resume_svc.record_reused_step(
                db,
                task=task, project_id=chapter.project_id, chapter_id=chapter.id,
                agent_name="RewriterAgent", step_name="rewrite",
                raw_output=resumed.final_text,
                note=f"retry_mode={retry_mode} 重用上次终稿",
            )
            final_text = resumed.final_text
            current_score = int((resumed.critic_report or {}).get("total") or final_score)
        else:
            final_text = draft_text
            current_score = final_score
        while (
            current_score < policy.pass_score
            and rewrite_rounds < policy.max_rewrite_rounds
            and not check.hard_conflicts
            and not resume_svc.should_skip_step(
                "rewrite",
                mode=retry_mode,
                last_succeeded=resumed.last_step,
                from_step=from_step,
            )
        ):
            await self._ensure_not_cancelled(db, task)
            rewrite_inputs = {
                "chapter_no": chapter.chapter_no,
                "draft_content": final_text,
                "critic_report": json.dumps(critic_report, ensure_ascii=False, indent=2),
                "detail_constraints": "\n".join(ctx_data.detail_guard_reminders) or "(无)",
                "chapter_plan": json.dumps(chapter_plan, ensure_ascii=False, indent=2),
            }
            rewrite_result = await rewriter.run(
                AgentContext(
                    db=db,
                    task=task,
                    project_id=chapter.project_id,
                    chapter_id=chapter.id,
                    inputs=rewrite_inputs,
                )
            )
            total_cost += rewrite_result.cost_usd
            total_in += rewrite_result.input_tokens
            total_out += rewrite_result.output_tokens
            total_dur += rewrite_result.duration_ms
            rewrite_rounds += 1
            rewritten = (rewrite_result.parsed or {}).get("rewritten_content") or final_text
            # Defensive: small models sometimes return a dict like
            # {"chapter_title": "...", "chapter_content": "..."} instead
            # of the requested `rewritten_content` field. Try a few
            # common alternative keys before falling back to final_text.
            if not isinstance(rewritten, str):
                parsed_rw = rewrite_result.parsed or {}
                for key in (
                    "rewritten_content",
                    "chapter_content",
                    "content",
                    "text",
                    "draft",
                    "body",
                ):
                    candidate = parsed_rw.get(key)
                    if isinstance(candidate, str) and candidate.strip():
                        rewritten = candidate
                        break
                else:
                    rewritten = final_text
            # re-run critic
            critic_inputs2 = dict(critic_inputs)
            critic_inputs2["draft_content"] = rewritten
            critic2 = await critic.run(
                AgentContext(
                    db=db,
                    task=task,
                    project_id=chapter.project_id,
                    chapter_id=chapter.id,
                    inputs=critic_inputs2,
                )
            )
            total_cost += critic2.cost_usd
            total_in += critic2.input_tokens
            total_out += critic2.output_tokens
            total_dur += critic2.duration_ms
            critic_report = critic2.parsed or {}
            current_score = int(critic_report.get("total") or 0)
            final_text = rewritten
            await self._save_version(
                db,
                chapter,
                f"rewrite_{rewrite_rounds}",
                rewritten,
                current_score,
                notes={"critic_after_rewrite": critic_report, "changes": (rewrite_result.parsed or {}).get("changes", [])},
            )
            if current_score >= policy.pass_score:
                break

        # 7) Continuity on the final text
        await self._ensure_not_cancelled(db, task)
        if resume_svc.should_skip_step(
            "continuity",
            mode=retry_mode,
            last_succeeded=resumed.last_step,
            from_step=from_step,
        ):
            await resume_svc.record_reused_step(
                db,
                task=task, project_id=chapter.project_id, chapter_id=chapter.id,
                agent_name="ContinuityAgent", step_name="continuity",
                note=f"retry_mode={retry_mode} 重用上次输出",
            )
        else:
            cont_agent = ContinuityAgent(self.router, self.engine)
            cont_inputs = {
                "draft_content": final_text,
                "memory_context": json.dumps(
                    {
                        "character_states": ctx_data.character_states,
                        "hard_facts": ctx_data.hard_facts,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "active_foreshadows": json.dumps(ctx_data.active_foreshadows, ensure_ascii=False, indent=2),
            }
            cont_result = await cont_agent.run(
                AgentContext(
                    db=db,
                    task=task,
                    project_id=chapter.project_id,
                    chapter_id=chapter.id,
                    inputs=cont_inputs,
                )
            )
            total_cost += cont_result.cost_usd
            total_in += cont_result.input_tokens
            total_out += cont_result.output_tokens
            total_dur += cont_result.duration_ms

        # 8) Memory update
        await self._ensure_not_cancelled(db, task)
        if resume_svc.should_skip_step(
            "memory_update",
            mode=retry_mode,
            last_succeeded=resumed.last_step,
            from_step=from_step,
        ):
            await resume_svc.record_reused_step(
                db,
                task=task, project_id=chapter.project_id, chapter_id=chapter.id,
                agent_name="MemoryUpdateAgent", step_name="memory_update",
                note=f"retry_mode={retry_mode} 重用上次输出",
            )
        else:
            mu_agent = MemoryUpdateAgent(self.router, self.engine)
            mu_inputs = {
                "final_content": final_text,
                "memory_context": json.dumps(
                    {
                        "characters_present": ctx_data.characters_present,
                        "character_states": ctx_data.character_states,
                        "active_foreshadows": ctx_data.active_foreshadows,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            }
            mu_result = await mu_agent.run(
                AgentContext(
                    db=db,
                    task=task,
                    project_id=chapter.project_id,
                    chapter_id=chapter.id,
                    inputs=mu_inputs,
                )
            )
            total_cost += mu_result.cost_usd
            total_in += mu_result.input_tokens
            total_out += mu_result.output_tokens
            total_dur += mu_result.duration_ms

        # 9) Learning reflection
        await self._ensure_not_cancelled(db, task)
        chapter.current_score = current_score
        chapter.actual_word_count = len(final_text)
        chapter.status = "done" if current_score >= policy.pass_score else "needs_review"
        await self._save_version(db, chapter, "final", final_text, current_score, notes={
            "rewrite_rounds": rewrite_rounds,
            "hard_conflicts": check.hard_conflicts,
        })

        if resume_svc.should_skip_step(
            "learning",
            mode=retry_mode,
            last_succeeded=resumed.last_step,
            from_step=from_step,
        ):
            await resume_svc.record_reused_step(
                db,
                task=task, project_id=chapter.project_id, chapter_id=chapter.id,
                agent_name="LearningAgent", step_name="learning",
                note=f"retry_mode={retry_mode} 重用上次输出",
            )
        else:
            learner = LearningAgent(self.router, self.engine)
            learn_inputs = {
                "chapter_summary": final_text[:600],
                "critic_report": json.dumps(critic_report, ensure_ascii=False, indent=2),
                "task_stats": json.dumps(
                    {
                        "cost_usd": round(total_cost, 4),
                        "input_tokens": total_in,
                        "output_tokens": total_out,
                        "duration_ms": total_dur,
                    },
                    ensure_ascii=False,
                ),
                "rewrite_history": json.dumps({"rounds": rewrite_rounds}, ensure_ascii=False),
            }
            learn_result = await learner.run(
                AgentContext(
                    db=db,
                    task=task,
                    project_id=chapter.project_id,
                    chapter_id=chapter.id,
                    inputs=learn_inputs,
                )
            )
            total_cost += learn_result.cost_usd
            total_in += learn_result.input_tokens
            total_out += learn_result.output_tokens
            total_dur += learn_result.duration_ms

        pass_status = "pass" if current_score >= policy.pass_score else "fail"
        await self._emit(
            db,
            task,
            chapter,
            "pipeline.completed",
            f"第 {chapter.chapter_no} 章完成，分数 {current_score}，状态 {pass_status}",
        )
        return ChapterPipelineResult(
            chapter_id=chapter.id,
            final_text=final_text,
            final_score=current_score,
            pass_status=pass_status,
            rewrite_rounds=rewrite_rounds,
            total_cost_usd=round(total_cost, 4),
            total_input_tokens=total_in,
            total_output_tokens=total_out,
            total_duration_ms=total_dur,
            hard_conflicts=check.hard_conflicts,
            issues=issues,
        )

    async def _ensure_not_cancelled(
        self, db: AsyncSession, task: AgentTask
    ) -> None:
        """P1-3 fix: abort the pipeline if the user cancelled the task.

        Previously the cancel endpoint only flipped the DB status to
        ``cancelled`` — the running pipeline had no way to find out and
        would happily burn through every remaining agent step. Now we
        refresh the row at every agent boundary and raise if the user
        asked us to stop. The worker's outer ``except`` block catches
        the RuntimeError, leaves the row in ``cancelled``, and
        publishes a ``task.cancelled`` event.

        The cancel check is cheap (one PK lookup + maybe a status
        refresh) so the latency cost is negligible compared to the
        multi-second LLM calls that follow.
        """
        # Refresh from DB so we see the latest status even if the
        # current session has a stale snapshot. ``db.refresh`` re-queries
        # only the columns of the instance we already loaded.
        await db.refresh(task)
        if task.status == "cancelled":
            raise RuntimeError(f"Task {task.id} was cancelled by user")

    async def _save_version(
        self,
        db: AsyncSession,
        chapter: Chapter,
        kind: str,
        content: str,
        score: int | None,
        notes: dict[str, Any] | None = None,
    ) -> None:
        # Defensive: if some upstream agent returned a dict instead of
        # a string (small models occasionally hallucinate schemas), try
        # to extract the prose before persisting.
        if not isinstance(content, str):
            for key in ("rewritten_content", "chapter_content", "content", "text", "body"):
                candidate = content.get(key) if isinstance(content, dict) else None
                if isinstance(candidate, str) and candidate.strip():
                    content = candidate
                    break
            else:
                # last resort: stringify whatever we got so the row is
                # still saved and we can debug from the raw blob.
                import json as _json
                content = _json.dumps(content, ensure_ascii=False, indent=2)
        existing = (
            await db.execute(
                select(ChapterVersion)
                .where(ChapterVersion.chapter_id == chapter.id, ChapterVersion.version_kind == kind)
                .order_by(ChapterVersion.version_no.desc())
            )
        ).scalars().all()
        next_no = (existing[0].version_no + 1) if existing else 1
        ver = ChapterVersion(
            chapter_id=chapter.id,
            version_kind=kind,
            version_no=next_no,
            content=content,
            score=score,
            notes=notes,
            summary=(content[:300] + "...") if len(content) > 300 else content,
        )
        db.add(ver)

    async def _emit(
        self,
        db: AsyncSession,
        task: AgentTask,
        chapter: Chapter,
        event_type: str,
        message: str,
        *,
        level: str = "info",
    ) -> None:
        from app.models.task import AgentEvent

        evt = AgentEvent(
            project_id=chapter.project_id,
            chapter_id=chapter.id,
            task_id=task.id,
            event_type=event_type,
            level=level,
            message=message,
        )
        db.add(evt)
        await db.flush()
        await event_bus.publish(
            Event(
                event_type=event_type,
                payload={
                    "project_id": chapter.project_id,
                    "chapter_id": chapter.id,
                    "task_id": task.id,
                    "message": message,
                    "level": level,
                },
            )
        )
