"""P6 §4.4 + P4 worker: 跑 DiscussionSession 的 participant + synthesis 轮次.

P3 DiscussionBridge.create_from_group 已经写了 DiscussionSession + meta turn
(status='running') + AgentTask (task_type=comment_discussion). P4 worker
拉起 task, 跑以下轮次:

  turn 1..N: 5 个 participant (按 group.participants 顺序, 每个对应一个 AgentRole)
  turn N+1: chief_synthesis (调 chief_main 或 discussion_synthesis prompt)

P4 这一轮走 stub 模式:
  - participant: 写 [P4 stub] 占位 turn (kind='participant'), 解析下一步真接 LLM
  - synthesis: 写 [P4 stub] chief_synthesis, 给一个默认 decision
  - 真正调 LLM 留 P4.1 — 跟 P3 §9 run_discussion_decision 的 stub 保持一致

完成后:
  - session.status = 'succeeded' (或 'partial' / 'failed')
  - group.status = 'decided'
  - group.decision = {decision, ...stub metadata}
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment_review import ReviewCommentGroup
from app.models.discussion import DiscussionSession, DiscussionTurn

logger = logging.getLogger(__name__)


# 默认 5 个参与者 (P3 discussion_bridge._select_participants 选出来的常见组合)
# 跟 AgentRole.key 一致, runner 可以直接 dispatch
DEFAULT_PARTICIPANTS: list[tuple[str, str]] = [
    ("planner", "策划"),
    ("drafter", "主笔"),
    ("critic", "审稿"),
    ("continuity", "连戏"),
    ("memory_update", "记忆"),
]


@dataclass
class DiscussionRunOutcome:
    """CommentDiscussionRunner.run_for_task 的结果."""

    session_id: int
    group_id: int
    turn_count: int
    participant_count: int
    synthesis_done: bool
    session_status: str  # succeeded / partial / failed
    error: str | None = None


class CommentDiscussionRunner:
    """跑 DiscussionSession 的所有轮次 — P4 stub 实现.

    P4.1 真接 LLM 时, 把 _run_one_participant / _run_synthesis 替换成
    AgentRoleRunner.run(agent_key, ...) 即可, 公共接口不变.
    """

    async def run_for_task(
        self,
        db: AsyncSession,
        *,
        task: Any,
    ) -> DiscussionRunOutcome:
        """从 task.payload 拿 session_id / group_id, 跑满轮次.

        task 是 AgentTask 实例, 走 type=Any 避免循环引用.
        """
        payload = task.payload or {}
        session_id = payload.get("session_id")
        group_id = payload.get("group_id")
        if session_id is None or group_id is None:
            return DiscussionRunOutcome(
                session_id=session_id or 0, group_id=group_id or 0,
                turn_count=0, participant_count=0, synthesis_done=False,
                session_status="failed",
                error="payload missing session_id or group_id",
            )

        # 1. 拉 session + group
        session = await db.get(DiscussionSession, session_id)
        group = await db.get(ReviewCommentGroup, group_id)
        if session is None:
            return DiscussionRunOutcome(
                session_id=session_id, group_id=group_id,
                turn_count=0, participant_count=0, synthesis_done=False,
                session_status="failed", error=f"DiscussionSession {session_id} not found",
            )
        if group is None:
            return DiscussionRunOutcome(
                session_id=session_id, group_id=group_id,
                turn_count=0, participant_count=0, synthesis_done=False,
                session_status="failed", error=f"ReviewCommentGroup {group_id} not found",
            )

        # 2. 决定 participants
        # session.participants 是 list[str] (agent keys)
        participant_keys: list[str] = list(session.participants or [])
        if not participant_keys:
            # 兜底: 用默认 5 个
            participant_keys = [k for k, _ in DEFAULT_PARTICIPANTS]
        participant_labels: dict[str, str] = dict(DEFAULT_PARTICIPANTS)

        # 3. 写 5 个 participant turns (stub)
        # turn_no 从 1 开始 (turn_no=0 已经被 P3 meta 占位)
        existing_turns = (await db.execute(
            select(DiscussionTurn).where(
                DiscussionTurn.session_id == session_id,
                DiscussionTurn.turn_no > 0,
            )
        )).scalars().all()
        existing_turn_nos = {t.turn_no for t in existing_turns}

        next_turn_no = 1
        for agent_key in participant_keys:
            if next_turn_no in existing_turn_nos:
                next_turn_no += 1
                continue
            await self._run_one_participant(
                db, session_id=session_id, turn_no=next_turn_no,
                agent_key=agent_key,
                role_label=participant_labels.get(agent_key, agent_key),
            )
            next_turn_no += 1
        participant_count = next_turn_no - 1

        # 4. 写 1 个 synthesis turn (stub)
        synthesis_turn_no = next_turn_no
        if synthesis_turn_no not in existing_turn_nos:
            await self._run_synthesis(
                db, session_id=session_id, turn_no=synthesis_turn_no,
                group=group,
            )
            synthesis_done = True
        else:
            synthesis_done = True  # 已存在, 视作完成

        # 5. 更新 session + group 状态
        session.status = "succeeded"
        group.status = "decided"
        group.decision = {
            "decision": "no_change",  # P4 stub 默认; P4.1 改用 chief_synthesis 解析
            "decision_source": "P4 stub",
            "stub_reason": "[P4 stub] 默认无变更, 真实裁决留 P4.1 (chief_synthesis 解析)",
            "decided_at": datetime.utcnow().isoformat(),
        }
        await db.flush()

        turn_count = (participant_count or 0) + (1 if synthesis_done else 0)
        logger.info(
            "comment_discussion: session=%s group=%s turns=%s status=succeeded",
            session_id, group_id, turn_count,
        )

        return DiscussionRunOutcome(
            session_id=session_id,
            group_id=group_id,
            turn_count=turn_count,
            participant_count=participant_count,
            synthesis_done=synthesis_done,
            session_status="succeeded",
        )

    # ---- stub: participant 轮 ----
    async def _run_one_participant(
        self,
        db: AsyncSession,
        *,
        session_id: int,
        turn_no: int,
        agent_key: str,
        role_label: str,
    ) -> None:
        """P4 stub: 写一个占位 participant turn.

        P4.1 真接 LLM 时:
          - 调 AgentRoleRunner.run(agent_key=agent_key, ...)
          - 拿回 parsed.perspective / key_points / concerns
          - 写 content + parsed
        """
        turn = DiscussionTurn(
            session_id=session_id,
            turn_no=turn_no,
            agent_name=f"{agent_key}_agent",
            role_label=role_label,
            kind="participant",
            content=(
                f"[P4 stub] {role_label} 视角占位 — 真实 LLM 调用留 P4.1."
                f" 预期调 AgentRoleRunner.run(agent_key='{agent_key}') 拿 perspective + key_points."
            ),
            parsed={
                "stub": True,
                "agent_key": agent_key,
                "expected_fields": ["perspective", "key_points", "concerns"],
            },
            error=None,
            duration_ms=0,
        )
        db.add(turn)
        await db.flush()

    # ---- stub: synthesis 轮 ----
    async def _run_synthesis(
        self,
        db: AsyncSession,
        *,
        session_id: int,
        turn_no: int,
        group: ReviewCommentGroup,
    ) -> None:
        turn = DiscussionTurn(
            session_id=session_id,
            turn_no=turn_no,
            agent_name="chief_agent",
            role_label="主 Agent",
            kind="synthesis",
            content=(
                "[P4 stub] 主 Agent 综合占位 — 真实 LLM 调 chief_main 拿 verdict."
                f"  评论组 #{group.id} severity={group.severity}."
            ),
            parsed={
                "stub": True,
                "decision": "no_change",
                "expected_fields": ["summary", "agreement", "tension", "recommendation", "next_actions"],
            },
            error=None,
            duration_ms=0,
        )
        db.add(turn)
        await db.flush()


_discussion_runner_singleton: CommentDiscussionRunner | None = None


def get_comment_discussion_runner() -> CommentDiscussionRunner:
    global _discussion_runner_singleton
    if _discussion_runner_singleton is None:
        _discussion_runner_singleton = CommentDiscussionRunner()
    return _discussion_runner_singleton


__all__ = [
    "CommentDiscussionRunner",
    "DiscussionRunOutcome",
    "get_comment_discussion_runner",
    "DEFAULT_PARTICIPANTS",
]
