"""Base class for DeepStudy stage executors."""
from abc import ABC, abstractmethod
from datetime import datetime, timezone


class BaseStage(ABC):
    stage_key: str = ""

    @abstractmethod
    async def execute_chapter(
        self, db, run, chapter_index: int, chapter_text: str, prev_context: dict | None = None
    ) -> dict:
        """Execute one chapter of this stage. Returns output dict or raises on failure."""
        ...

    async def execute_stage(self, db, run, stage_result_store):
        """Execute the full stage across all chapters. Updates run progress."""
        from app.models.study import StudyChapter
        from sqlalchemy import select

        chapters_result = await db.execute(
            select(StudyChapter).where(
                StudyChapter.material_id == run.material_id
            ).order_by(StudyChapter.chapter_index)
        )
        chapters = chapters_result.scalars().all()

        run.processed_chapters = 0
        run.total_chapters = len(chapters)

        for ch in chapters:
            try:
                result = await self.execute_chapter(db, run, ch.chapter_index, ch.content or "")
                # Save stage result
                from app.models.deepstudy import DeepStudyStageResult
                sr = DeepStudyStageResult(
                    run_id=run.id,
                    material_id=run.material_id,
                    chapter_id=ch.id,
                    chapter_index=ch.chapter_index,
                    stage_key=self.stage_key,
                    status="succeeded",
                    output_json=result,
                    input_tokens=result.get("_input_tokens", 0),
                    output_tokens=result.get("_output_tokens", 0),
                    cost_usd=result.get("_cost_usd", 0),
                    duration_ms=result.get("_duration_ms", 0),
                )
                db.add(sr)
                run.processed_chapters = (run.processed_chapters or 0) + 1
            except Exception as e:
                from app.models.deepstudy import DeepStudyStageResult
                sr = DeepStudyStageResult(
                    run_id=run.id,
                    material_id=run.material_id,
                    chapter_id=ch.id,
                    chapter_index=ch.chapter_index,
                    stage_key=self.stage_key,
                    status="failed",
                    error_message=str(e),
                )
                db.add(sr)
                # Continue to next chapter, don't fail the whole run

        # Mark stage as completed in run progress
        if not isinstance(run.progress, dict):
            run.progress = {}
        completed = list(run.progress.get("completed_stages", []) or [])
        if self.stage_key not in completed:
            completed.append(self.stage_key)
        run.progress["completed_stages"] = completed

        await db.commit()
