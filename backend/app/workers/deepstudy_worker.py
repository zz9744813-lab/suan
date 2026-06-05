"""DeepStudy worker — polls for queued/running StudyRun rows and
advances them through the DAG, one stage per tick.

Called every ~10s from the main worker loop (worker.py).
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.database import session_scope
from app.models.deepstudy import StudyRun
from app.services.deepstudy.coordinator import DeepStudyCoordinatorAgent


async def deepstudy_tick() -> None:
    """Called every ~10s by the main worker loop.

    Fetches all queued / running StudyRun rows and advances
    each one by a single stage tick.
    """
    coordinator = DeepStudyCoordinatorAgent()

    # Fetch run IDs in a quick session
    run_ids: list[int] = []
    try:
        async with session_scope() as db:
            result = await db.execute(
                select(StudyRun.id).where(
                    StudyRun.status.in_(["queued", "running"])
                ).order_by(StudyRun.id)
            )
            run_ids = [row[0] for row in result.all()]
    except Exception as e:
        print(f"[deepstudy_worker] Error fetching runs: {e}")
        return

    if not run_ids:
        return

    # Process each run — one per tick, serialised to avoid DB contention
    for run_id in run_ids:
        try:
            await coordinator.execute_run(run_id)
        except Exception as e:
            print(f"[deepstudy_worker] Error processing run {run_id}: {e}")
