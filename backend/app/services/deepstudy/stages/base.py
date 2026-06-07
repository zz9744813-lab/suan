"""Base class for DeepStudy stage executors."""
import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime

_log = logging.getLogger(__name__)

# 进度同步到数据库的间隔 (每处理多少个章节同步一次)
_PROGRESS_SYNC_INTERVAL = 10


class BaseStage(ABC):
    stage_key: str = ""

    @abstractmethod
    async def execute_chapter(
        self, db, run, chapter_index: int, chapter_text: str, prev_context: dict | None = None
    ) -> dict:
        """Execute one chapter of this stage. Returns output dict or raises on failure."""
        ...

    async def execute_stage(self, db, run, stage_result_store):
        """Execute the full stage across all chapters with checkpointing.

        Each chapter runs in its own session so LLM waits do not hold a
        long write transaction. Existing successful chapter results are
        skipped, which makes a crashed 800+ chapter run resumable.

        Performance notes (2026-06 SQLite optimization pass):
        - WAL mode enabled in database.py → read/write no longer block each other
        - Per-chapter COUNT queries removed → in-memory counters instead
        - Progress sync reduced from every-chapter to every-10-chapters
        - Concurrency raised from 3 to 5 (safe under WAL mode)
        """
        from sqlalchemy import func, select
        from app.core.database import session_scope
        from app.models.deepstudy import DeepStudyStageResult, StudyRun
        from app.models.study import StudyChapter

        chapters_result = await db.execute(
            select(StudyChapter).where(
                StudyChapter.material_id == run.material_id
            ).order_by(StudyChapter.chapter_index)
        )
        chapters = chapters_result.scalars().all()

        run.total_chapters = len(chapters)
        succeeded_indexes = set((await db.execute(
            select(DeepStudyStageResult.chapter_index).where(
                DeepStudyStageResult.run_id == run.id,
                DeepStudyStageResult.stage_key == self.stage_key,
                DeepStudyStageResult.status == "succeeded",
            )
        )).scalars().all())
        run.processed_chapters = len(succeeded_indexes)
        progress = dict(run.progress or {}) if isinstance(run.progress, dict) else {}
        progress["current_stage"] = self.stage_key
        progress.setdefault("stage_totals", {})[self.stage_key] = {
            "total": len(chapters),
            "succeeded": len(succeeded_indexes),
            "pending": max(0, len(chapters) - len(succeeded_indexes)),
            "failed": 0,
        }
        run.progress = progress
        await db.commit()

        pending = [ch for ch in chapters if ch.chapter_index not in succeeded_indexes]
        plan = run.agent_plan if isinstance(run.agent_plan, dict) else {}
        concurrency = int(plan.get("chapter_concurrency") or plan.get("concurrency") or 5)
        # WAL 模式下并发写入安全, 上限 8; 非 WAL 环境建议降到 3
        concurrency = max(1, min(concurrency, 8))
        sem = asyncio.Semaphore(concurrency)

        # ── 内存计数器 (替代每章 2 次 COUNT 查询) ──
        # 初始值 = 本次 execute_stage 开始前已有的成功/失败数
        mem_succeeded = len(succeeded_indexes)
        mem_failed = 0
        mem_since_last_sync = 0

        async def _sync_progress_to_db():
            """将内存计数器同步到数据库 (每 N 个章节调用一次)."""
            nonlocal mem_since_last_sync
            try:
                async with session_scope() as sync_db:
                    sync_run = await sync_db.get(StudyRun, run.id)
                    if sync_run is None:
                        return
                    sync_run.processed_chapters = mem_succeeded
                    sync_progress = dict(sync_run.progress or {}) if isinstance(sync_run.progress, dict) else {}
                    sync_progress["current_stage"] = self.stage_key
                    sync_progress.setdefault("stage_totals", {})[self.stage_key] = {
                        "total": len(chapters),
                        "succeeded": mem_succeeded,
                        "pending": max(0, len(chapters) - mem_succeeded - mem_failed),
                        "failed": mem_failed,
                    }
                    sync_run.progress = sync_progress
                mem_since_last_sync = 0
            except Exception as exc:
                _log.warning("Progress sync failed (non-fatal): %s", exc)

        async def process_chapter(chapter_id: int, chapter_index: int, chapter_text: str) -> None:
            nonlocal mem_succeeded, mem_failed, mem_since_last_sync

            async with sem:
                # SQLite "database is locked" retry: WAL 模式下极少触发,
                # 但保留作为安全网
                from sqlalchemy.exc import OperationalError
                import random as _random
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        async with session_scope() as local_db:
                            local_run = await local_db.get(StudyRun, run.id)
                            if local_run is None:
                                return
                            existing = (await local_db.execute(
                                select(DeepStudyStageResult)
                                .where(
                                    DeepStudyStageResult.run_id == run.id,
                                    DeepStudyStageResult.stage_key == self.stage_key,
                                    DeepStudyStageResult.chapter_index == chapter_index,
                                )
                                .order_by(DeepStudyStageResult.id.desc())
                            )).scalars().first()
                            if existing is not None and existing.status == "succeeded":
                                return
                            if existing is None:
                                existing = DeepStudyStageResult(
                                    run_id=run.id,
                                    material_id=run.material_id,
                                    chapter_id=chapter_id,
                                    chapter_index=chapter_index,
                                    stage_key=self.stage_key,
                                    status="running",
                                    input_snapshot={
                                        "chapter_index": chapter_index,
                                        "content_chars": len(chapter_text or ""),
                                    },
                                )
                                local_db.add(existing)
                            else:
                                existing.status = "running"
                                existing.error_message = None
                                existing.retry_count = (existing.retry_count or 0) + 1
                                existing.input_snapshot = {
                                    "chapter_index": chapter_index,
                                    "content_chars": len(chapter_text or ""),
                                }
                            existing.updated_at = datetime.utcnow()
                            await local_db.flush()

                            try:
                                result = await self.execute_chapter(
                                    local_db, local_run, chapter_index, chapter_text or ""
                                )
                                existing.status = "succeeded"
                                existing.output_json = result
                                existing.raw_output = None
                                existing.error_message = None
                                existing.input_tokens = int(result.get("_input_tokens", 0) or 0)
                                existing.output_tokens = int(result.get("_output_tokens", 0) or 0)
                                existing.cost_usd = float(result.get("_cost_usd", 0) or 0)
                                existing.duration_ms = int(result.get("_duration_ms", 0) or 0)
                                mem_succeeded += 1
                            except Exception as exc:
                                existing.status = "failed"
                                existing.error_message = str(exc)[:4000]
                                mem_failed += 1
                            existing.updated_at = datetime.utcnow()

                            # ── 进度同步: 每 N 个章节同步一次 ──
                            mem_since_last_sync += 1
                            if mem_since_last_sync >= _PROGRESS_SYNC_INTERVAL:
                                await _sync_progress_to_db()

                        # 成功完成, 跳出 retry 循环
                        break
                    except OperationalError as oexc:
                        if "database is locked" in str(oexc) and attempt < max_retries - 1:
                            await asyncio.sleep(0.5 * (2 ** attempt) + _random.uniform(0, 0.2))
                            continue
                        raise

        if pending:
            await asyncio.gather(*[
                process_chapter(ch.id, ch.chapter_index, ch.content or "")
                for ch in pending
            ])

        # ── 最终同步: 把剩余的计数器刷到数据库 ──
        if mem_since_last_sync > 0:
            await _sync_progress_to_db()

        # ── 阶段完成后的最终统计 (在主 session 里, 只查一次) ──
        await db.refresh(run)
        succeeded_count = (await db.execute(
            select(func.count()).select_from(DeepStudyStageResult).where(
                DeepStudyStageResult.run_id == run.id,
                DeepStudyStageResult.stage_key == self.stage_key,
                DeepStudyStageResult.status == "succeeded",
            )
        )).scalar_one()
        failed_count = (await db.execute(
            select(func.count()).select_from(DeepStudyStageResult).where(
                DeepStudyStageResult.run_id == run.id,
                DeepStudyStageResult.stage_key == self.stage_key,
                DeepStudyStageResult.status == "failed",
            )
        )).scalar_one()
        sums = (await db.execute(
            select(
                func.coalesce(func.sum(DeepStudyStageResult.input_tokens), 0),
                func.coalesce(func.sum(DeepStudyStageResult.output_tokens), 0),
                func.coalesce(func.sum(DeepStudyStageResult.cost_usd), 0.0),
            ).where(DeepStudyStageResult.run_id == run.id)
        )).one()
        run.input_tokens = int(sums[0] or 0)
        run.output_tokens = int(sums[1] or 0)
        run.cost_usd = round(float(sums[2] or 0.0), 6)
        run.processed_chapters = int(succeeded_count or 0)

        progress = dict(run.progress or {}) if isinstance(run.progress, dict) else {}
        completed = list(progress.get("completed_stages", []) or [])
        if self.stage_key not in completed:
            completed.append(self.stage_key)
        progress["completed_stages"] = completed
        progress["current_stage"] = self.stage_key
        progress.setdefault("stage_totals", {})[self.stage_key] = {
            "total": len(chapters),
            "succeeded": int(succeeded_count or 0),
            "pending": max(0, len(chapters) - int(succeeded_count or 0) - int(failed_count or 0)),
            "failed": int(failed_count or 0),
        }
        run.progress = progress

        await db.commit()
