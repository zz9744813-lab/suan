"""P0 修复: 把历史的 comment_cleanup / heartbeat 任务标 internal。

之前 visibility 字段不规范, 现在统一标 internal, 防止用户任务页
刷屏。 同时回填 domain / task_kind。
"""
import asyncio
import logging

from sqlalchemy import select, update

from app.core.database import session_scope
from app.models.task import AgentTask

logging.disable(logging.CRITICAL)


async def main() -> None:
    async with session_scope() as db:
        # comment_cleanup 全部标 internal + domain=review + task_kind=comment_cleanup
        res1 = await db.execute(
            update(AgentTask)
            .where(AgentTask.task_type == "comment_cleanup")
            .where(AgentTask.visibility != "internal")
            .values(visibility="internal", domain="review", task_kind="comment_cleanup")
        )
        print(f"  comment_cleanup: {res1.rowcount} rows -> internal/review")

        # 兜底: 任何 task_type 是 'comment_cleanup' 也要把 retry_mode 之类清掉
        # (暂时不写, 避免动业务字段)

        # 把历史遗留的 heartbeat / cleanup / audit_cleanup 标 internal
        for t in ("heartbeat", "cleanup", "audit_cleanup"):
            res = await db.execute(
                update(AgentTask)
                .where(AgentTask.task_type == t)
                .where(AgentTask.visibility != "internal")
                .values(visibility="internal", domain="system", task_kind=t)
            )
            print(f"  {t}: {res.rowcount} rows -> internal/system")

        # 把"已失败"的 comment_cleanup 也保留 (用户调试时要看)
        # 所以不删, 只标 internal

        # 把目前还存在没 domain 的写任务标 domain=writing
        # (待写任务: 1-2h 内准备跑的 chapter pipeline 任务)
        res2 = await db.execute(
            update(AgentTask)
            .where(AgentTask.domain.is_(None))
            .where(AgentTask.task_type.in_([
                "write_chapter", "revise_chapter", "rewrite_from_discussion",
                "plan_chapter", "out_chapter",
            ]))
            .values(domain="writing")
        )
        print(f"  domain=writing 回填: {res2.rowcount} rows")

        # 拆分 (study) 任务也回填 domain
        res3 = await db.execute(
            update(AgentTask)
            .where(AgentTask.domain.is_(None))
            .where(AgentTask.task_type.like("study_%"))
            .values(domain="deepstudy")
        )
        print(f"  domain=deepstudy 回填 (study_*): {res3.rowcount} rows")

        res4 = await db.execute(
            update(AgentTask)
            .where(AgentTask.domain.is_(None))
            .where(AgentTask.task_type.in_(["deepstudy_run"]))
            .values(domain="deepstudy")
        )
        print(f"  domain=deepstudy 回填 (deepstudy_run): {res4.rowcount} rows")


if __name__ == "__main__":
    asyncio.run(main())
