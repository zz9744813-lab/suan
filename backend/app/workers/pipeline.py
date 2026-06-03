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
from app.models.task import AgentTask, WorkerPolicy
from app.services.context_compiler import ContextCompiler, get_context_compiler
from app.services.detail_guard import DetailCheckResult, get_detail_guard
from app.services.llm.router import LLMRouter, get_llm_router
from app.services.prompt_engine import PromptEngine, get_prompt_engine


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

        # 1) ContextCompiler
        ctx_data = await self.compiler.compile(db, chapter=chapter, policy=policy)
        ctx_inputs = self.compiler.to_prompt_inputs(ctx_data)

        # 2) Planner
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

        # 3) Drafter
        drafter = DrafterAgent(self.router, self.engine)
        drafter_inputs = {
            "chapter_no": chapter.chapter_no,
            "title": chapter.title,
            "target_word_count": chapter.target_word_count,
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
            "behavior_patterns": "(暂无行为模式，可参考主角/女主标签)",
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

        # 5) Critic
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
        rewriter = RewriterAgent(self.router, self.engine)
        rewrite_rounds = 0
        final_text = draft_text
        current_score = final_score
        while (
            current_score < policy.pass_score
            and rewrite_rounds < policy.max_rewrite_rounds
            and not check.hard_conflicts
        ):
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
        chapter.current_score = current_score
        chapter.actual_word_count = len(final_text)
        chapter.status = "done" if current_score >= policy.pass_score else "needs_review"
        await self._save_version(db, chapter, "final", final_text, current_score, notes={
            "rewrite_rounds": rewrite_rounds,
            "hard_conflicts": check.hard_conflicts,
        })

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
