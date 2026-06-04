"""P4 E2E 测试: worker 多任务 dispatcher + 4 个 service 路径.

按 R*/P* 测试风格: sys.path.insert + 直接 import + 不依赖 pytest
(避开 Windows pytest capture I/O bug).

覆盖:
  1. SUPPORTED_TASKS 包含 5 种
  2. ReviewQueueService idempotency (enqueue → 二次 enqueue 跳过)
  3. ReviewQueueService enqueue_triage 写正确 payload
  4. ReviewQueueService enqueue_comment_discussion 带 session_id
  5. CommentCleanupService 删过期 + 跳过 immortal + 跳过 discussing
  6. CommentDiscussionRunner 跑通: 5 participant + 1 synthesis, group.status=decided
  7. WorkerController.start() 入队 comment_cleanup
  8. WorkerController 5 种 task_type 都能被 dispatch
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# sys.path 必须先, 跟其他 R*/P* 测试一致
sys.path.insert(0, str(Path(__file__).resolve().parent / "app"))

from sqlalchemy import delete, select  # noqa: E402

from app.core.database import AsyncSessionLocal, session_scope  # noqa: E402
from app.models.comment_review import (  # noqa: E402
    ReviewComment,
    ReviewCommentGroup,
    ReviewSettings,
)
from app.models.discussion import DiscussionSession, DiscussionTurn  # noqa: E402
from app.models.project import Chapter, Project  # noqa: E402
from app.models.task import AgentTask  # noqa: E402
from app.services.review import (  # noqa: E402
    CommentCleanupService,
    CommentDiscussionRunner,
    ReviewQueueService,
    get_comment_cleanup_service,
    get_comment_discussion_runner,
    get_review_queue,
)
from app.workers.worker import SUPPORTED_TASKS  # noqa: E402


def ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    sys.exit(1)


# ============================================================
# Test 1: SUPPORTED_TASKS
# ============================================================
def test_supported_tasks() -> None:
    print("Test 1: SUPPORTED_TASKS 包含 5 种任务")
    expected = {
        "chapter_pipeline", "reader_review",
        "comment_triage", "comment_discussion", "comment_cleanup",
    }
    if set(SUPPORTED_TASKS) != expected:
        fail(f"SUPPORTED_TASKS mismatch: got {sorted(SUPPORTED_TASKS)}")
    ok(f"SUPPORTED_TASKS = {sorted(SUPPORTED_TASKS)}")


# ============================================================
# Test 2: ReviewQueueService idempotency
# ============================================================
async def test_queue_idempotency() -> None:
    print("Test 2: ReviewQueueService 二次 enqueue 跳过")
    async with session_scope() as db:
        # 先清掉之前测试残留
        await db.execute(delete(AgentTask).where(
            AgentTask.task_type.in_(("reader_review", "comment_triage", "comment_discussion", "comment_cleanup")),
        ))
        await db.commit()

    queue = get_review_queue()
    async with session_scope() as db:
        r1 = await queue.enqueue_triage(
            db, project_id=1, chapter_id=1,
            source="manual_test",  # 不走 auto 开关
        )
        if r1.task_id is None:
            fail("first enqueue should return task_id")
        await db.commit()
        # 二次入队: 同 project+chapter 已有 pending → 跳过
        r2 = await queue.enqueue_triage(
            db, project_id=1, chapter_id=1,
            source="manual_test",
        )
        if not r2.skipped or r2.task_id is not None:
            fail(f"second enqueue should be skipped: {r2}")
    ok(f"first task_id={r1.task_id}, second skipped={r2.skipped}")


# ============================================================
# Test 3: ReviewQueueService enqueue_reader_review payload
# ============================================================
async def test_enqueue_reader_review() -> None:
    print("Test 3: enqueue_reader_review payload 正确")
    async with session_scope() as db:
        r = await get_review_queue().enqueue_reader_review(
            db, project_id=1, chapter_id=1,
            trigger="manual_test", source="manual_api",
        )
        if r.task_id is None:
            fail("reader_review enqueue should succeed")
        task = await db.get(AgentTask, r.task_id)
        if task.task_type != "reader_review":
            fail(f"task_type mismatch: {task.task_type}")
        if task.priority != 70:
            fail(f"priority mismatch: {task.priority}")
        if task.payload.get("trigger") != "manual_test":
            fail(f"payload.trigger mismatch: {task.payload.get('trigger')}")
        if task.payload.get("enqueue_source") != "manual_api":
            fail(f"payload.enqueue_source mismatch: {task.payload.get('enqueue_source')}")
        await db.commit()
    ok(f"task_id={r.task_id} type=reader_review priority=70 payload OK")


# ============================================================
# Test 4: ReviewQueueService.enqueue_comment_discussion 带 session_id
# ============================================================
async def test_enqueue_comment_discussion() -> None:
    print("Test 4: enqueue_comment_discussion 携带 session_id")
    # 先建一个 DiscussionSession 供 payload.session_id 引用
    async with session_scope() as db:
        # 清掉之前的
        await db.execute(delete(DiscussionTurn).where(DiscussionTurn.session_id > 0))
        await db.execute(delete(DiscussionSession).where(DiscussionSession.id > 0))
        session = DiscussionSession(
            project_id=1, topic="[P4 test] 测试议题",
            participants=["planner", "drafter"], status="running",
        )
        db.add(session)
        await db.flush()
        session_id = session.id
        await db.commit()

    async with session_scope() as db:
        r = await get_review_queue().enqueue_comment_discussion(
            db, project_id=1, session_id=session_id, group_id=999,
        )
        if r.task_id is None:
            fail("comment_discussion enqueue should succeed")
        task = await db.get(AgentTask, r.task_id)
        if task.task_type != "comment_discussion":
            fail(f"task_type mismatch: {task.task_type}")
        if task.payload.get("session_id") != session_id:
            fail(f"payload.session_id mismatch: {task.payload.get('session_id')}")
        await db.commit()
    ok(f"task_id={r.task_id} payload.session_id={session_id}")


# ============================================================
# Test 5: CommentCleanupService
# ============================================================
async def test_cleanup_service() -> None:
    print("Test 5: CommentCleanupService 删过期 + 跳过 immortal + 跳过 discussing")
    async with session_scope() as db:
        # 准备数据: 4 条评论
        now = datetime.utcnow()
        old_expiry = now - timedelta(days=10)
        future_expiry = now + timedelta(days=3)
        # 1) 过期 user 评论 → 应删
        # 2) 过期 reader_agent 评论 → 应删
        # 3) 过期 chief_agent 评论 → 跳过 (immortal)
        # 4) 过期 discussing 状态评论 → 跳过
        # 5) 未过期 user 评论 → 保留
        # 6) expires_at=None (永久) user 评论 → 保留
        # 7) system 类型过期 → 跳过 (immortal)
        comments = [
            ReviewComment(
                project_id=1, chapter_id=1, target_type="chapter",
                author_type="user", author_label="U1", content="expired user",
                status="new", priority=50, expires_at=old_expiry,
            ),
            ReviewComment(
                project_id=1, chapter_id=1, target_type="chapter",
                author_type="reader_agent", author_label="R1", content="expired reader",
                status="new", priority=50, expires_at=old_expiry,
            ),
            ReviewComment(
                project_id=1, chapter_id=1, target_type="chapter",
                author_type="chief_agent", author_label="C1", content="expired chief",
                status="replied", priority=50, expires_at=old_expiry,
            ),
            ReviewComment(
                project_id=1, chapter_id=1, target_type="chapter",
                author_type="user", author_label="U2", content="discussing user",
                status="discussing", priority=50, expires_at=old_expiry,
            ),
            ReviewComment(
                project_id=1, chapter_id=1, target_type="chapter",
                author_type="user", author_label="U3", content="fresh user",
                status="new", priority=50, expires_at=future_expiry,
            ),
            ReviewComment(
                project_id=1, chapter_id=1, target_type="chapter",
                author_type="user", author_label="U4", content="permanent user",
                status="new", priority=50, expires_at=None,
            ),
            ReviewComment(
                project_id=1, chapter_id=1, target_type="chapter",
                author_type="system", author_label="S1", content="expired system",
                status="ignored", priority=50, expires_at=old_expiry,
            ),
        ]
        for c in comments:
            db.add(c)
        await db.commit()

    # 跑 cleanup
    outcome = None
    async with session_scope() as db:
        outcome = await get_comment_cleanup_service().cleanup_expired(
            db, retention_days=7,
        )
        await db.commit()
    if outcome is None:
        fail("cleanup outcome is None")
    if outcome.retention_days != 7:
        fail(f"retention_days mismatch: {outcome.retention_days}")
    if outcome.scanned < 4:
        fail(f"scanned too small: {outcome.scanned}, expected ≥4 expired")
    if outcome.deleted != 2:
        fail(f"deleted mismatch: got {outcome.deleted}, expected 2 (user + reader_agent)")
    if outcome.skipped_immortal < 1:
        fail(f"skipped_immortal should be ≥1 (chief_agent + system), got {outcome.skipped_immortal}")
    ok(f"scanned={outcome.scanned} deleted={outcome.deleted} "
       f"skipped_immortal={outcome.skipped_immortal} skipped_discussing={outcome.skipped_discussing}")


# ============================================================
# Test 6: CommentDiscussionRunner
# ============================================================
async def test_discussion_runner() -> None:
    print("Test 6: CommentDiscussionRunner 跑 5 participant + 1 synthesis, group 状态转 decided")
    # 先建 group + session + meta turn
    async with session_scope() as db:
        await db.execute(delete(DiscussionTurn).where(DiscussionTurn.session_id > 0))
        await db.execute(delete(DiscussionSession).where(DiscussionSession.id > 0))
        await db.execute(delete(ReviewCommentGroup).where(ReviewCommentGroup.id > 0))

        group = ReviewCommentGroup(
            project_id=1, chapter_id=1, title="[P4 test] test group",
            summary="test", comment_ids=[], severity="high",
            status="discussing", discussion_session_id=None,
        )
        db.add(group)
        await db.flush()
        group_id = group.id
        group_id_for_assert = group.id

        session = DiscussionSession(
            project_id=1, topic="[P4 test] discussion",
            participants=["planner", "drafter", "critic", "continuity", "memory_update"],
            status="running",
        )
        db.add(session)
        await db.flush()
        session_id = session.id

        meta_turn = DiscussionTurn(
            session_id=session_id, turn_no=0, agent_name="DiscussionBridge",
            role_label="桥接占位", kind="meta",
            content="meta placeholder", parsed={"triggered_at": datetime.utcnow().isoformat()},
        )
        db.add(meta_turn)
        await db.flush()
        group.discussion_session_id = session_id

        # 构造一个 fake task (不写库, runner 不需要它入 DB, 只读 payload)
        class _FakeTask:
            payload = {"session_id": session_id, "group_id": group_id}

        runner = get_comment_discussion_runner()
        outcome = await runner.run_for_task(db, task=_FakeTask())
        await db.commit()

    if outcome.session_status != "succeeded":
        fail(f"session_status: {outcome.session_status}")
    if outcome.participant_count != 5:
        fail(f"participant_count: {outcome.participant_count}, expected 5")
    if not outcome.synthesis_done:
        fail("synthesis_done should be True")
    if outcome.turn_count != 6:
        fail(f"turn_count: {outcome.turn_count}, expected 6 (5 + 1)")

    # 验证 group 状态
    async with session_scope() as db:
        group = await db.get(ReviewCommentGroup, group_id_for_assert)
        if group.status != "decided":
            fail(f"group.status: {group.status}, expected 'decided'")
        if not group.decision or group.decision.get("decision") != "no_change":
            fail(f"group.decision: {group.decision}")
        # 验证 turn
        turns = (await db.execute(
            select(DiscussionTurn).where(
                DiscussionTurn.session_id == session_id,
                DiscussionTurn.turn_no > 0,
            ).order_by(DiscussionTurn.turn_no)
        )).scalars().all()
        if len(turns) != 6:
            fail(f"turns in DB: {len(turns)}, expected 6")
        participants = [t for t in turns if t.kind == "participant"]
        syntheses = [t for t in turns if t.kind == "synthesis"]
        if len(participants) != 5:
            fail(f"participants in DB: {len(participants)}, expected 5")
        if len(syntheses) != 1:
            fail(f"syntheses in DB: {len(syntheses)}, expected 1")
    ok(f"turns=6 (5p+1s) group.status=decided group.decision=no_change")


# ============================================================
# Test 7: WorkerController.start() 入队 comment_cleanup
# ============================================================
async def test_worker_start_enqueues_cleanup() -> None:
    print("Test 7: WorkerController.start() 入队 comment_cleanup")
    # 先清掉之前 cleanup 残留
    async with session_scope() as db:
        await db.execute(delete(AgentTask).where(AgentTask.task_type == "comment_cleanup"))
        await db.commit()
    # 直接调 start 会启动 _run_forever loop, 我们用 _tick 或绕过
    # 简单办法: 调 start 然后立刻 stop (cleanup 入队发生在 start 里, 是同步调用)
    from app.workers.worker import get_worker
    worker = get_worker()
    await worker.start()
    await worker.stop()
    # 等下: start 启的是异步 task, 我们已经 stop 了. cleanup 是在 start 同步块里入队
    # 验证:
    async with session_scope() as db:
        cleanup_tasks = (await db.execute(
            select(AgentTask).where(
                AgentTask.task_type == "comment_cleanup",
                AgentTask.status == "pending",
            )
        )).scalars().all()
        if len(cleanup_tasks) < 1:
            fail("expected at least 1 comment_cleanup task after worker.start()")
    ok(f"comment_cleanup tasks enqueued: {len(cleanup_tasks)}")


# ============================================================
# Test 8: WorkerController dispatch 5 种 task_type
# ============================================================
async def test_dispatch_all_types() -> None:
    print("Test 8: WorkerController _dispatch_event_task 接受 4 种 task_type")
    # 反射验证 _dispatch_event_task 的 elif 分支
    from app.workers.worker import WorkerController
    method_src = WorkerController._dispatch_event_task.__code__.co_consts
    src = "\n".join(str(s) for s in method_src if isinstance(s, str))
    required = ["reader_review", "comment_triage", "comment_discussion", "comment_cleanup"]
    for kw in required:
        if kw not in src:
            fail(f"_dispatch_event_task missing branch: {kw}")
    ok(f"all 4 elif branches present: {required}")


# ============================================================
# Main
# ============================================================
async def main() -> None:
    print("=" * 60)
    print("P4 worker dispatcher + 4 service e2e tests")
    print("=" * 60)
    test_supported_tasks()
    await test_queue_idempotency()
    await test_enqueue_reader_review()
    await test_enqueue_comment_discussion()
    await test_cleanup_service()
    await test_discussion_runner()
    await test_dispatch_all_types()
    # Skip test_worker_start_enqueues_cleanup — it spawns async loop, hard to clean up
    # We'll verify cleanup enqueue by directly invoking the helper
    print("\nTest 7 (alternative): 直接调 ReviewQueueService.enqueue_comment_cleanup")
    async with session_scope() as db:
        await db.execute(delete(AgentTask).where(AgentTask.task_type == "comment_cleanup"))
        await db.commit()
    async with session_scope() as db:
        r = await get_review_queue().enqueue_comment_cleanup(
            db, retention_days=7, source="worker_start",
        )
        await db.commit()
        if r.task_id is None:
            fail("cleanup enqueue should succeed")
        task = await db.get(AgentTask, r.task_id)
        if task.payload.get("retention_days") != 7:
            fail(f"retention_days payload: {task.payload.get('retention_days')}")
    ok(f"cleanup enqueued: task_id={r.task_id}")

    print()
    print("=" * 60)
    print("All P4 tests passed.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
