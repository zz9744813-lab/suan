"""DeepStudyCoordinatorAgent — the main execution loop.

Consumes one tick per call per run, advancing the DAG one stage
at a time. Stages with registered handlers execute real chapter-level
processing; stages without handlers fall back to simulated completion.

Auto-linkage: after marking a stage complete the coordinator
publishes ``stage_completed`` so the GraphMaterializer and other
consumers can materialise the output without explicit dispatch.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.core.database import session_scope
from app.models.deepstudy import StudyRun
from app.models.project import Project
from app.models.study import StudyChapter, StudyMaterial
from app.models.task import AgentTask

from .auto_repair import AutoRepair
from .behavior_miner import BehaviorPatternMiner
from .event_bus import deepstudy_event_bus
from .graph_materializer import GraphMaterializer
from .job_graph import DEEPSTUDY_DAG, get_downstream_stages, get_ready_stages
from .knowledge_indexer import KnowledgeIndexer
from .stage_result_store import StageResultStore
from .stages.behavior_pattern_mine import BehaviorPatternMineStage
from .stages.chapter_profiler import ChapterProfilerStage
from .stages.entity_extractor import EntityExtractorStage
from .stages.event_extractor import EventExtractorStage
from .stages.relationship_analyze import RelationshipAnalyzeStage
from .stages.scene_beat_extractor import SceneBeatExtractorStage
from .stages.technique_mine import TechniqueMineStage
from .technique_miner import TechniqueMiner
from .writing_context_sync import WritingContextSync


_SCRATCH_PROJECT_NAME = "__NF2_SYSTEM_DEEPSTUDY__"


class DeepStudyCoordinatorAgent:
    """Orchestrates one DeepStudy run through the DAG.

    One coordinator instance handles one ``execute_run`` tick per
    invocation. The worker loop calls ``execute_run`` for every
    queued / running run, consuming one stage per tick.
    """

    def __init__(self) -> None:
        self.stage_store = StageResultStore()
        self.graph_materializer = GraphMaterializer()
        self.behavior_miner = BehaviorPatternMiner()
        self.technique_miner = TechniqueMiner()
        self.knowledge_indexer = KnowledgeIndexer()
        self.writing_sync = WritingContextSync()
        self.auto_repair = AutoRepair()
        # Stage handlers — map stage_key to real executor
        self.stage_handlers = {
            "chapter_profile": ChapterProfilerStage(),
            "entity_extract": EntityExtractorStage(),
            "event_extract": EventExtractorStage(),
            "scene_beat_extract": SceneBeatExtractorStage(),
            "relationship_analyze": RelationshipAnalyzeStage(),
            "behavior_pattern_mine": BehaviorPatternMineStage(),
            "technique_mine": TechniqueMineStage(),
        }

    async def execute_run(self, run_id: int) -> None:
        """Main execution loop — consume one tick per call.

        Each tick:
        1. Load the run, material, and current progress.
        2. Determine which stages are ready.
        3. Execute the next ready stage (one per tick).
        4. Publish stage_completed for auto-linkage.
        5. If all stages done, mark run as succeeded and run
           the finaliser chain (graph_finalize, study_critic,
           knowledge_index, writing_context_sync).
        """
        async with session_scope() as db:
            run = await db.get(StudyRun, run_id)
            if run is None:
                return
            if run.status not in ("queued", "running"):
                return

            # P0-D: Stub detection is handled by UI warnings. Users should configure real providers.

            completed_stages: list[str] = []
            if run.progress and isinstance(run.progress, dict):
                completed_stages = run.progress.get("completed_stages", [])

            ready = get_ready_stages(completed_stages)
            if not ready:
                # All stages done — finalise
                await self._finalize_run(db, run, completed_stages)
                return

            # Take the first ready stage
            next_stage = ready[0]

            # Transition to running if queued
            if run.status == "queued":
                run.status = "running"
                run.started_at = datetime.now(timezone.utc)

            run.current_stage = next_stage

            # Count total chapters for progress tracking
            material = await db.get(StudyMaterial, run.material_id)
            if material is not None:
                chapter_count_result = await db.execute(
                    select(func.count()).select_from(StudyChapter).where(
                        StudyChapter.material_id == run.material_id
                    )
                )
                run.total_chapters = chapter_count_result.scalar() or 0

            if run.total_chapters == 0:
                # No chapters — skip stage
                await self._advance_stage(db, run, next_stage)
                return

            # R28: ensure a user-visible parent task exists for this run
            existing = await db.execute(
                select(AgentTask).where(AgentTask.run_id == run_id, AgentTask.visibility == "user")
            )
            if not existing.scalar_one_or_none():
                chapters_count = run.total_chapters or 0
                title_value = f"DeepStudy《{material.title if material else 'Material #' + str(run.material_id)}》"
                project_id = await self._resolve_task_project_id(db, run, material)
                parent_task = AgentTask(
                    task_type="deepstudy_run",
                    project_id=project_id,
                    visibility="user",
                    domain="deepstudy",
                    task_kind="deepstudy_material_run",
                    material_id=run.material_id,
                    run_id=run.id,
                    display_title=title_value,
                    status="running",
                    progress_current=0,
                    progress_total=chapters_count,
                )
                db.add(parent_task)

            # Execute the stage (real dispatch if handler exists, fallback otherwise)
            await self._execute_stage(db, run, next_stage)

    async def _resolve_task_project_id(self, db, run: StudyRun, material: StudyMaterial | None) -> int:
        """DeepStudy tasks need a non-null project even for global books."""
        if run.project_id:
            return run.project_id
        if material and material.project_id:
            run.project_id = material.project_id
            return material.project_id

        row = (await db.execute(
            select(Project).where(Project.name == _SCRATCH_PROJECT_NAME)
        )).scalar_one_or_none()
        if row is None:
            # P0 修复: 显式打系统标记, 让 GET /api/projects 默认隐藏。
            # 旧版 name="拆书·公共" 会被小说项目页看到, 用户困扰。
            row = Project(
                name=_SCRATCH_PROJECT_NAME,
                genre="system",
                category="__system_deepstudy",
                status="system",
                description="系统内部项目：承载未绑定正式项目的 DeepStudy 任务，不在项目书架展示。",
            )
            db.add(row)
            await db.flush()
        run.project_id = row.id
        return row.id

    async def _execute_stage(self, db, run, stage_key: str) -> None:
        """Execute a single stage.

        Dispatches to the registered stage handler if one exists.
        Falls back to simulating completion for stages without handlers yet.
        """
        # Dispatch to real handler if available
        handler = self.stage_handlers.get(stage_key)
        if handler:
            await handler.execute_stage(db, run, self.stage_store)
        else:
            # Fallback: mark as completed (for stages without handlers yet)
            progress = dict(run.progress or {}) if isinstance(run.progress, dict) else {}
            completed = list(progress.get("completed_stages", []) or [])
            if stage_key not in completed:
                completed.append(stage_key)
            progress["completed_stages"] = completed
            progress["current_stage"] = stage_key
            run.progress = progress
            run.processed_chapters = run.total_chapters

        # Common: publish event for auto-linkage
        await deepstudy_event_bus.stage_completed(
            material_id=run.material_id,
            run_id=run.id,
            stage_key=stage_key,
            payload={"status": "completed"},
        )

        # Auto-materialise after specific stages
        await self._auto_materialize(run.material_id, stage_key)

        # R28: update parent task progress and cost
        parent_result = await db.execute(
            select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.visibility == "user")
        )
        parent = parent_result.scalar_one_or_none()
        if parent is not None:
            parent.progress_current = run.processed_chapters or 0
            parent.progress_total = run.total_chapters or 0
            parent.cost_usd = run.cost_usd or 0
            parent.input_tokens = run.input_tokens or 0

        # Check if the full DAG is done. Upload-triggered automation should
        # finish the entire study pipeline, not stop after the early core
        # extraction stages.
        completed = (run.progress or {}).get("completed_stages", [])
        all_stages = list(DEEPSTUDY_DAG.keys())
        if all(s in completed for s in all_stages):
            await self._finalize_run(db, run, completed)

        await db.flush()

    async def _advance_stage(self, db, run, stage_key: str) -> None:
        """Skip a stage when there are no chapters to process."""
        progress = dict(run.progress or {}) if isinstance(run.progress, dict) else {}
        completed: list[str] = list(progress.get("completed_stages", []) or [])
        if stage_key not in completed:
            completed.append(stage_key)
        progress["completed_stages"] = completed
        progress["current_stage"] = stage_key
        run.progress = progress

        await deepstudy_event_bus.stage_completed(
            material_id=run.material_id,
            run_id=run.id,
            stage_key=stage_key,
            payload={"status": "skipped", "reason": "no_chapters"},
        )
        await db.flush()

    async def _auto_materialize(self, material_id: int, stage_key: str) -> None:
        """Trigger auto-materialisation hooks after specific stages."""
        try:
            if stage_key == "entity_extract":
                await self.graph_materializer.materialize_stage_output(material_id, stage_key)
            elif stage_key == "event_extract":
                await self.graph_materializer.materialize_stage_output(material_id, stage_key)
            elif stage_key == "relationship_analyze":
                await self.graph_materializer.materialize_stage_output(material_id, stage_key)
            elif stage_key == "scene_beat_extract":
                await self.graph_materializer.materialize_stage_output(material_id, stage_key)
            elif stage_key == "behavior_pattern_mine":
                await self.graph_materializer.materialize_stage_output(material_id, stage_key)
            elif stage_key == "foreshadow_analyze":
                await self.graph_materializer.materialize_stage_output(material_id, stage_key)
            elif stage_key == "technique_mine":
                await self.graph_materializer.materialize_stage_output(material_id, stage_key)
        except Exception:
            # Materialisation failure should not block stage advancement.
            pass

    async def _finalize_run(self, db, run, completed_stages: list[str]) -> None:
        """All stages complete — run finalisers and mark run succeeded."""
        material_id = run.material_id
        all_stages = list(DEEPSTUDY_DAG.keys())

        if not all(s in completed_stages for s in all_stages):
            return  # Not truly done — some stages may be unreachable

        try:
            # Graph finalisation
            await self.graph_materializer.finalize_graph(material_id, db=db)
            # Behaviour pattern consolidation
            await self.behavior_miner.finalize_book_patterns(material_id, db=db)
            # Technique consolidation
            await self.technique_miner.finalize_techniques(material_id, db=db)
            # Knowledge indexing
            await self.knowledge_indexer.index_material(material_id, db=db)
            # Writing context sync
            await self.writing_sync.sync_material(material_id, db=db)

            # Mark material as completed
            from app.models.study import StudyMaterial
            material = await db.get(StudyMaterial, material_id)
            if material is not None:
                material.study_status = "completed"
                material.last_deepstudied_at = datetime.now(timezone.utc)

            run.status = "succeeded"
            run.finished_at = datetime.now(timezone.utc)

            # R28: mark parent task as succeeded
            parent_result = await db.execute(
                select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.visibility == "user")
            )
            parent = parent_result.scalar_one_or_none()
            if parent is not None:
                parent.status = "succeeded"
                parent.progress_current = run.processed_chapters or 0
                parent.progress_total = run.total_chapters or 0
                parent.cost_usd = run.cost_usd or 0
                parent.input_tokens = run.input_tokens or 0
                parent.finished_at = run.finished_at

            await deepstudy_event_bus.stage_completed(
                material_id=material_id,
                run_id=run.id,
                stage_key="run_completed",
                payload={"status": "succeeded"},
            )
        except Exception as e:
            run.status = "failed"
            run.error = str(e)
            run.finished_at = datetime.now(timezone.utc)

            # R28: mark parent task as failed
            parent_result = await db.execute(
                select(AgentTask).where(AgentTask.run_id == run.id, AgentTask.visibility == "user")
            )
            parent = parent_result.scalar_one_or_none()
            if parent is not None:
                parent.status = "failed"
                parent.error = str(e)[:500]
                parent.finished_at = run.finished_at

            await deepstudy_event_bus.stage_completed(
                material_id=material_id,
                run_id=run.id,
                stage_key="run_failed",
                payload={"status": "failed", "error": str(e)},
            )

        await db.flush()
