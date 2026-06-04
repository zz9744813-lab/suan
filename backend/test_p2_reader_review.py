"""P2 验收脚本 — 调 ReaderReviewService 在 chapter 13 上跑 reader_review.

验收目标 (plan §13 P2):
  - 5 个 reader Agent 都能跑
  - 写 5 条 author_type='reader_agent' 的 ReviewComment
  - ReaderReviewRun.status='succeeded' (or 'partial' if some failed)
  - 每条 ReviewComment 关联 agent_role_id / evidence / rating

注意: 这一步会真打 LLM (whitedream / step-3.7-flash) 5 次, 预算 ~$0.05.
若想跑 mock: 把 ReviewSettings.auto_reader_review 关掉, 然后直接
调 ReaderReviewService.run_for_chapter(trigger='manual_test') 即可 (mock
provider 默认会返回 _mock_chat 的占位 JSON, 仍然会写 5 条 ReviewComment,
但 content 是 stub 文本 — 用来验证流程, 不能验证 prompt 质量).
"""
import asyncio
import json

from app.core.database import session_scope
from app.models.comment_review import (
    ReaderAgentProfile,
    ReaderReviewRun,
    ReviewComment,
)
from app.services.review import get_reader_review_service


async def main() -> None:
    # chapter 13 / project 1 / version 46 (final v3, 4384 chars, score 80)
    project_id = 1
    chapter_id = 13
    chapter_version_id = 46

    async with session_scope() as db:
        svc = get_reader_review_service()
        outcome = await svc.run_for_chapter(
            db,
            project_id=project_id,
            chapter_id=chapter_id,
            chapter_version_id=chapter_version_id,
            trigger="manual_test",
        )
        print("\n=== ReaderReviewOutcome ===")
        print(json.dumps({
            "run_id": outcome.run_id,
            "status": outcome.status,
            "chapter_id": outcome.chapter_id,
            "chapter_version_id": outcome.chapter_version_id,
            "attempted": outcome.reader_keys_attempted,
            "succeeded": outcome.reader_keys_succeeded,
            "failed": outcome.reader_keys_failed,
            "comment_ids": outcome.comment_ids,
            "total_input_tokens": outcome.total_input_tokens,
            "total_output_tokens": outcome.total_output_tokens,
            "total_cost_usd": outcome.total_cost_usd,
            "error": outcome.error,
        }, ensure_ascii=False, indent=2))

        # 详细看每条 comment
        if outcome.comment_ids:
            from sqlalchemy import select
            comments = (await db.execute(
                select(ReviewComment).where(ReviewComment.id.in_(outcome.comment_ids))
            )).scalars().all()
            print(f"\n=== {len(comments)} ReviewComment(s) ===")
            for c in comments:
                print(f"\n--- comment id={c.id} ({c.author_label}, severity={c.tags}) ---")
                print(f"  content[:200]: {c.content[:200]!r}")
                print(f"  rating: {c.rating}")
                print(f"  weight_at_created: {c.weight_at_created}")
                print(f"  expires_at: {c.expires_at}")

        # 验证 ReaderReviewRun
        run = await db.get(ReaderReviewRun, outcome.run_id)
        print(f"\n=== ReaderReviewRun #{run.id} ===")
        print(f"  status: {run.status}")
        print(f"  trigger: {run.trigger}")
        print(f"  reader_agent_keys: {run.reader_agent_keys}")
        print(f"  generated_comment_ids: {run.generated_comment_ids}")
        print(f"  total_cost_usd: {run.total_cost_usd}")
        print(f"  total_input_tokens: {run.total_input_tokens}")
        print(f"  total_output_tokens: {run.total_output_tokens}")
        print(f"  started_at: {run.started_at}")
        print(f"  finished_at: {run.finished_at}")
        print(f"  error: {run.error}")

        # ReaderAgentProfile 状态
        from sqlalchemy import select as sql_select
        profiles = (await db.execute(
            sql_select(ReaderAgentProfile)
        )).scalars().all()
        print(f"\n=== {len(profiles)} ReaderAgentProfile(s) ===")
        for p in profiles:
            print(f"  {p.reader_key:20s} weight={p.weight:.3f}  generated={p.generated_comment_count}  last_used={p.last_used_at}")


if __name__ == "__main__":
    asyncio.run(main())
