"""Mark internal study tasks as visibility=internal and create parent tasks for DeepStudy runs."""
import asyncio

from sqlalchemy import select, update

from app.core.database import session_scope
from app.models.deepstudy import StudyRun
from app.models.study import StudyMaterial
from app.models.task import AgentTask


async def migrate():
    async with session_scope() as db:
        # 1. Mark study_character/study_event/etc as internal
        internal_types = ["study_character", "study_event", "study_relationship", "study_behavior", "model_call"]
        for t in internal_types:
            await db.execute(
                update(AgentTask).where(AgentTask.task_type == t).values(
                    visibility="internal", domain="deepstudy", stage_key=t
                )
            )
        print(f"Migrated internal task types")

        # 2. Create parent tasks for completed DeepStudy runs
        runs_result = await db.execute(
            select(StudyRun).where(StudyRun.status == "succeeded")
        )
        runs = runs_result.scalars().all()
        for run in runs:
            existing = await db.execute(
                select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.visibility == "user")
            )
            if existing.scalar_one_or_none():
                continue
            material_result = await db.execute(
                select(StudyMaterial).where(StudyMaterial.id == run.material_id)
            )
            mat = material_result.scalar_one_or_none()
            title = f"DeepStudy《{mat.title if mat else '?'}》"
            if run.project_id is None:
                print(f"  Skipping run {run.id} ({title}) — no project_id")
                continue
            parent = AgentTask(
                task_type="deepstudy_run",
                project_id=run.project_id,
                visibility="user",
                domain="deepstudy",
                task_kind="deepstudy_material_run",
                material_id=run.material_id,
                run_id=run.id,
                display_title=title,
                status="succeeded",
                progress_current=run.processed_chapters or 0,
                progress_total=run.total_chapters or 0,
                cost_usd=run.cost_usd or 0,
                input_tokens=run.input_tokens or 0,
            )
            db.add(parent)
            print(f"Created parent task for {title}")
        await db.commit()


asyncio.run(migrate())
