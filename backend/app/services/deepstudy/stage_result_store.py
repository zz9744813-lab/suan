"""Stage result store — persists per-stage results for audit and repair.

In the MVP the results are stored in the StudyRun's ``progress`` JSON
field (per-stage chapter counters) and in the ChapterAnalysis rows.
A future revision can add a dedicated ``deepstudy_stage_results`` table
for richer per-chapter output tracking.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.core.database import session_scope
from app.models.deepstudy import ChapterAnalysis, StudyRun


class StageResultStore:
    """Persists per-stage results for a DeepStudy run.

    Uses the existing StudyRun.progress JSON field for stage-level
    tracking and ChapterAnalysis rows for per-chapter output.
    """

    async def save(
        self,
        run_id: int,
        material_id: int,
        stage_key: str,
        chapter_index: int,
        status: str,
        output_json: dict[str, Any] | None = None,
        error_message: str | None = None,
        tokens: int = 0,
        cost: float = 0.0,
    ) -> None:
        """Save a single chapter's stage result.

        Reads the existing run to find the correct chapter_id for
        the given chapter_index, then creates/updates a ChapterAnalysis
        row. Also updates the run's token/cost counters.
        """
        async with session_scope() as db:
            run = await db.get(StudyRun, run_id)
            if run is None:
                return

            # Find the chapter_id for this chapter_index
            from app.models.study import StudyChapter
            chapter = (
                await db.execute(
                    select(StudyChapter).where(
                        StudyChapter.material_id == material_id,
                        StudyChapter.chapter_index == chapter_index,
                    )
                )
            ).scalar_one_or_none()

            if chapter is None:
                return

            # Upsert ChapterAnalysis
            existing = (
                await db.execute(
                    select(ChapterAnalysis).where(
                        ChapterAnalysis.run_id == run_id,
                        ChapterAnalysis.chapter_id == chapter.id,
                        ChapterAnalysis.chapter_index == chapter_index,
                    )
                )
            ).scalar_one_or_none()

            if existing:
                existing.status = status
                existing.error = error_message
                if output_json:
                    existing.raw_result = output_json
            else:
                analysis = ChapterAnalysis(
                    run_id=run_id,
                    material_id=material_id,
                    chapter_id=chapter.id,
                    chapter_index=chapter_index,
                    status=status,
                    raw_result=output_json,
                    error=error_message,
                )
                db.add(analysis)

            # Update run counters
            run.input_tokens = (run.input_tokens or 0) + tokens
            run.output_tokens = (run.output_tokens or 0) + tokens
            run.cost_usd = round((run.cost_usd or 0.0) + cost, 6)

    async def get_stage_results(
        self,
        material_id: int,
        stage_key: str,
    ) -> list[dict[str, Any]]:
        """Get all results for a stage across all runs on this material.

        Returns a list of ChapterAnalysis rows serialised as dicts.
        """
        async with session_scope() as db:
            rows = (
                await db.execute(
                    select(ChapterAnalysis).where(
                        ChapterAnalysis.material_id == material_id,
                    )
                )
            ).scalars().all()

            return [
                {
                    "run_id": r.run_id,
                    "chapter_id": r.chapter_id,
                    "chapter_index": r.chapter_index,
                    "status": r.status,
                    "summary": r.summary,
                    "narrative_function": r.narrative_function,
                    "pov": r.pov,
                    "tone": r.tone,
                    "error": r.error,
                }
                for r in rows
            ]

    async def get_failed_stages(self, run_id: int) -> list[dict[str, Any]]:
        """Get all failed stages for a run (for repair)."""
        async with session_scope() as db:
            rows = (
                await db.execute(
                    select(ChapterAnalysis).where(
                        ChapterAnalysis.run_id == run_id,
                        ChapterAnalysis.status == "failed",
                    )
                )
            ).scalars().all()

            return [
                {
                    "id": r.id,
                    "chapter_id": r.chapter_id,
                    "chapter_index": r.chapter_index,
                    "error": r.error,
                }
                for r in rows
            ]

    async def mark_stage_done(self, run_id: int, stage_key: str) -> None:
        """Mark all chapters in this stage as done (succeeded)."""
        async with session_scope() as db:
            run = await db.get(StudyRun, run_id)
            if run is None:
                return

            progress = run.progress or {}
            if isinstance(progress, dict):
                completed = progress.get("completed_stages", [])
                if stage_key not in completed:
                    completed.append(stage_key)
                    progress["completed_stages"] = completed
                    run.progress = progress
