"""Learning service: minimal post-chapter reflection.

Spec §13. MVP version: collects per-step cost/score, persists a learning
record. Future phases will add pattern mining and prompt evolution.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Chapter
from app.models.task import AgentStep, AgentTask


@dataclass
class LearningRecord:
    chapter_no: int
    final_score: int | None
    pass_score: int
    pass_status: str  # pass / fail / borderline
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    total_duration_ms: int
    rewrite_rounds: int
    conflicts: int
    suggestions: list[str]


class LearningService:
    async def reflect(
        self,
        db: AsyncSession,
        *,
        chapter: Chapter,
        pass_score: int,
    ) -> LearningRecord:
        steps = (
            await db.execute(
                select(AgentStep)
                .where(AgentStep.chapter_id == chapter.id)
            )
        ).scalars().all()

        total_cost = sum(s.cost_usd for s in steps)
        total_in = sum(s.input_tokens for s in steps)
        total_out = sum(s.output_tokens for s in steps)
        total_dur = sum(s.duration_ms for s in steps)
        rewrite_rounds = sum(1 for s in steps if s.step_name == "rewrite")
        conflicts = sum(1 for s in steps if "DetailGuard" in s.agent_name and s.parsed_output and s.parsed_output.get("hard_conflicts"))

        score = chapter.current_score
        if score is None:
            status = "unknown"
        elif score >= pass_score:
            status = "pass"
        elif score >= pass_score - 10:
            status = "borderline"
        else:
            status = "fail"

        suggestions: list[str] = []
        if status == "fail":
            suggestions.append("考虑针对本章触发改稿讨论。")
        if conflicts > 0:
            suggestions.append("存在硬冲突：更新 DetailGuard 写前清单。")
        if rewrite_rounds >= 2:
            suggestions.append("Rewrite 轮数过高：检查 Planner 输出的可执行性。")

        return LearningRecord(
            chapter_no=chapter.chapter_no,
            final_score=score,
            pass_score=pass_score,
            pass_status=status,
            total_cost_usd=round(total_cost, 4),
            total_input_tokens=total_in,
            total_output_tokens=total_out,
            total_duration_ms=total_dur,
            rewrite_rounds=rewrite_rounds,
            conflicts=conflicts,
            suggestions=suggestions,
        )
