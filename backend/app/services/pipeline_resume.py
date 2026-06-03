"""Pipeline resume service (P15 / P0-RETRY-1).

When a Task fails, the user clicks "重试" and picks a retry mode:

  - ``full``                 — rerun the entire pipeline from scratch
  - ``from_failed_step``     — reuse the last-succeeded step's output and
                               resume from the one that failed
  - ``critic_only``          — keep the existing plan + draft, rerun the
                               Critic and everything after
  - ``continue_with_fallback`` — Critic returned unparseable JSON last
                               time. Synthesise a fallback critic_report
                               at ``pass_score`` and continue straight to
                               Continuity / MemoryUpdate / Learning so
                               the chapter still produces a final.

This service is the source of truth for "what state was left behind".
It pulls from two tables:
  - ``agent_steps``  — plan / draft / review (Critic) / rewrite / cont /
                       memory_update / learning rows carry the last
                       successful parsed_output / raw_output
  - ``chapter_versions`` — final / rewrite_N rows carry the last
                       committed prose

NOTE on step_name: agents write their ``step_name`` class attribute
into ``agent_steps.step_name`` as-is, regardless of how many times
they ran. So we always see ONE ``"review"`` row and ONE ``"rewrite"``
row per task — they represent the LATEST invocation. The round count
is implicit in the critic / rewriter output (e.g. the latest rewrite
was round 2 if max_rewrite_rounds ≥ 2 was reached).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Chapter, ChapterVersion
from app.models.task import AgentStep, AgentTask


# Canonical step ordering — used both for the resume algorithm (find
# the first step that's NOT succeeded) and for writing the "reused"
# placeholder rows so the AgentStepRail shows the same progression
# the user would see on a fresh run.
#
# ``context_compile`` is special: it has no AgentStep row (it runs
# inside ContextCompiler.compile()). We still list it so the
# should_skip_step() anchor is well-defined.
STEP_ORDER: list[str] = [
    "context_compile",
    "plan",
    "draft",
    "review",         # CriticAgent.step_name
    "rewrite",        # RewriterAgent.step_name (latest round)
    "continuity",
    "memory_update",
    "learning",
]


@dataclass
class ResumedState:
    """Snapshot of what the previous run produced.

    Every field defaults to ``None`` so a partial run (e.g. only the
    plan finished) still produces a valid ResumedState. ``last_step``
    is the name of the highest ``STEP_ORDER`` step that succeeded
    (or ``None`` if nothing did).
    """
    plan: dict[str, Any] | None = None
    draft_text: str | None = None
    critic_report: dict[str, Any] | None = None
    final_text: str | None = None
    last_step: str | None = None
    # Per-step metadata for the resume algorithm: maps step_name -> (AgentStep.id, parsed_output, raw_output).
    by_step: dict[str, tuple[int, dict[str, Any] | None, str | None]] = field(default_factory=dict)


class PipelineResumeService:
    """Load the previous run's outputs and let the pipeline skip work."""

    async def load_previous_outputs(
        self,
        db: AsyncSession,
        *,
        task: AgentTask,
        chapter: Chapter,
    ) -> ResumedState:
        """Walk ``agent_steps`` and surface the highest-succeeded
        step's outputs."""
        # 1. Pull all steps for this task in id order (chronological).
        steps = (
            await db.execute(
                select(AgentStep)
                .where(AgentStep.task_id == task.id)
                .order_by(AgentStep.id.asc())
            )
        ).scalars().all()

        # 2. Reduce to the LAST occurrence of each step_name (a
        #    retried run produces multiple rows; we only want the
        #    newest "succeeded" one). If a step is currently in
        #    status='running' (e.g. retry kicked in mid-step), we
        #    IGNORE it and use the previous successful one.
        latest: dict[str, AgentStep] = {}
        for s in steps:
            latest[s.step_name] = s  # last wins because of ASC + iteration

        succeeded: dict[str, AgentStep] = {
            k: v for k, v in latest.items() if v.status == "succeeded"
        }

        # 3. Translate to ResumedState.
        state = ResumedState()
        for step_name, s in latest.items():
            state.by_step[step_name] = (s.id, s.parsed_output, s.raw_output)

        plan_step = succeeded.get("plan")
        if plan_step is not None and isinstance(plan_step.parsed_output, dict):
            state.plan = plan_step.parsed_output

        draft_step = succeeded.get("draft")
        if draft_step is not None:
            # Drafter doesn't use JSON; raw_output is the prose.
            state.draft_text = (draft_step.raw_output or "").strip() or None

        critic_step = succeeded.get("review")
        if critic_step is not None and isinstance(critic_step.parsed_output, dict):
            state.critic_report = critic_step.parsed_output

        # Final text: prefer the latest rewrite's raw_output; fall
        # back to draft if no rewrite ran. Both ChapterVersion and
        # the agent's raw_output are valid sources — we trust the
        # agent step here because it always reflects the LATEST
        # critic/rewrite decision.
        rewrite_step = succeeded.get("rewrite")
        if rewrite_step is not None and rewrite_step.raw_output:
            state.final_text = rewrite_step.raw_output
        elif state.draft_text:
            state.final_text = state.draft_text

        # 4. Compute last_step — the last STEP_ORDER entry that's
        #    succeeded. Used by ``from_failed_step`` to know where to
        #    resume from.
        for step_name in reversed(STEP_ORDER):
            if step_name in succeeded:
                state.last_step = step_name
                break

        return state

    async def record_reused_step(
        self,
        db: AsyncSession,
        *,
        task: AgentTask,
        project_id: int,
        chapter_id: int | None,
        agent_name: str,
        step_name: str,
        raw_output: str | None = None,
        parsed_output: dict[str, Any] | None = None,
        note: str = "",
    ) -> AgentStep:
        """Insert an AgentStep row with status='reused' for a step the
        pipeline is SKIPPING on this retry.

        Distinct from ``status='succeeded'`` (real LLM call) and
        ``status='failed'``. The AgentStepRail renders it as "↺" so
        the user can tell what was actually new vs. carried over.
        """
        step = AgentStep(
            task_id=task.id,
            project_id=project_id,
            chapter_id=chapter_id,
            agent_name=agent_name,
            step_name=step_name,
            status="reused",
            raw_output=raw_output,
            parsed_output=parsed_output,
            error_message=note or None,
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            duration_ms=0,
        )
        db.add(step)
        await db.flush()
        return step

    def should_skip_step(
        self,
        step_name: str,
        *,
        mode: str,
        last_succeeded: str | None,
        from_step: str | None,
    ) -> bool:
        """Decide whether the pipeline can skip ``step_name`` given the
        active retry mode.

        Returns True if the step's output is already in ResumedState
        and we can reuse it without re-calling the LLM.
        """
        if mode == "full":
            return False
        if mode == "critic_only":
            # Reuse plan / draft; rerun critic + everything after.
            return step_name in ("context_compile", "plan", "draft")
        if mode == "continue_with_fallback":
            # Critic failed last time; we synthesise a fallback
            # critic_report and rerun continuity / memory / learning.
            # Plan / draft / critic are reused.
            return step_name in ("context_compile", "plan", "draft", "review")
        if mode == "from_failed_step":
            # Skip any step whose position is BEFORE the
            # last-succeeded one (or ``from_step`` if explicitly set).
            anchor = from_step or _next_step_after(last_succeeded)
            if anchor is None:
                return False
            try:
                anchor_idx = STEP_ORDER.index(anchor)
            except ValueError:
                return False
            try:
                step_idx = STEP_ORDER.index(step_name)
            except ValueError:
                return False
            return step_idx < anchor_idx
        return False


def _next_step_after(step_name: str | None) -> str | None:
    """Return the STEP_ORDER entry that follows ``step_name``."""
    if step_name is None:
        return STEP_ORDER[0] if STEP_ORDER else None
    try:
        idx = STEP_ORDER.index(step_name)
    except ValueError:
        return None
    if idx + 1 < len(STEP_ORDER):
        return STEP_ORDER[idx + 1]
    return None


# Re-export for convenience.
__all__ = [
    "PipelineResumeService",
    "ResumedState",
    "STEP_ORDER",
    "_next_step_after",
]
