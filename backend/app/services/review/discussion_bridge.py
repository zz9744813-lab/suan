"""P3: DiscussionBridge — ReviewCommentGroup → DiscussionSession 桥接.

工作流 (P6 spec §4.4):
  1. 收集 group.comment_ids 对应的 ReviewComment (含 content / author_type)
  2. 按参与者策略 (spec §4.4 表) 选 participants:
     - 人物动机/情绪问题 → planner, drafter, critic, continuity
     - 设定硬伤/伏笔冲突 → planner, critic, continuity, memory
     - 节奏/商业留存    → planner, drafter, critic
     - 毒点/台词/解释腔 → drafter, critic
     - 大范围结构问题   → planner, drafter, critic, continuity, memory
  3. 写议题 (P6 spec §4.4 格式):
     ```
     来源: 评论区自动生成
     对象: <project> / 第 N 章《<title>》/ 终稿 v<n>
     关联评论: ...
     请讨论: 是否值得修改? 轻修/局部返工/大返工? ...
     ```
  4. 创建 DiscussionSession (status='running')
  5. 写 1 条 DiscussionTurn (kind='meta', 占位) — 真正跑 participant + synthesis
     由 P4 worker 接管, P3 bridge 只搭骨架
  6. group.discussion_session_id = session.id
  7. group.status = 'discussing'
  8. 入队 AgentTask (task_type='comment_discussion', payload={session_id, group_id})

入口:
  DiscussionBridge.create_from_group(db, group)
  → DiscussionSession

为什么不直接调 discussion router 的 run_discussion:
  - router 函数要 FastAPI Depends, 不能直接 await
  - 我们要自己控制 transaction 边界 (group + session 必须在同一 session 提交)
  - discussion router 是用户手动触发的入口, bridge 是 P3 主 Agent 触发的入口
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import not_found
from app.models.comment_review import (
    ReviewComment,
    ReviewCommentGroup,
)
from app.models.discussion import DiscussionSession, DiscussionTurn
from app.models.project import Chapter, ChapterVersion, Project
from app.models.task import AgentTask

logger = logging.getLogger(__name__)


# 标签 → 参与者策略
# 一个 group 可能命中多个 tag, 取并集去重
TAG_PARTICIPANT_MAP: dict[str, list[str]] = {
    # 人物动机/情绪问题
    "人物动机":   ["planner", "drafter", "critic", "continuity"],
    "情绪递进":   ["planner", "drafter", "critic", "continuity"],
    "关系变化":   ["planner", "drafter", "critic", "continuity"],
    # 设定硬伤/伏笔冲突
    "设定硬伤":   ["planner", "critic", "continuity", "memory"],
    "伏笔冲突":   ["planner", "critic", "continuity", "memory"],
    "吃书":       ["planner", "critic", "continuity", "memory"],
    "时间线":     ["planner", "critic", "continuity", "memory"],
    # 节奏/商业留存
    "节奏":       ["planner", "drafter", "critic"],
    "钩子":       ["planner", "drafter", "critic"],
    "留存":       ["planner", "drafter", "critic"],
    "付费点":     ["planner", "drafter", "critic"],
    "章末钩子":   ["planner", "drafter", "critic"],
    "爆点":       ["planner", "drafter", "critic"],
    # 毒点/台词/解释腔
    "劝退":       ["drafter", "critic"],
    "违和":       ["drafter", "critic"],
    "解释腔":     ["drafter", "critic"],
    "台词":       ["drafter", "critic"],
    "三观":       ["drafter", "critic"],
    # 大范围结构问题
    "结构":       ["planner", "drafter", "critic", "continuity", "memory"],
    "大纲":       ["planner", "drafter", "critic", "continuity", "memory"],
}

# severity 决定 default 参与者
SEVERITY_DEFAULT_PARTICIPANTS: dict[str, list[str]] = {
    "low":     ["drafter", "critic"],
    "medium":  ["planner", "drafter", "critic", "continuity"],
    "high":    ["planner", "drafter", "critic", "continuity", "memory"],
    "blocker": ["planner", "drafter", "critic", "continuity", "memory"],
}

# 兜底
FALLBACK_PARTICIPANTS = ["planner", "critic", "continuity"]


class DiscussionBridge:
    async def create_from_group(
        self,
        db: AsyncSession,
        group: ReviewCommentGroup,
    ) -> DiscussionSession:
        """把 ReviewCommentGroup 升级成 DiscussionSession 占位.

        P3 这一步只搭骨架, 真正跑 participant + synthesis 由 P4 worker 接管。
        """
        if group.id is None:
            raise ValueError("group must be flushed before creating discussion")
        if group.discussion_session_id is not None:
            # 已存在, 直接返回 (idempotent)
            existing = await db.get(DiscussionSession, group.discussion_session_id)
            if existing is not None:
                return existing

        # 1. 拉 group.comment_ids 对应评论
        comment_ids = list(group.comment_ids or [])
        comments: list[ReviewComment] = []
        if comment_ids:
            comments = (await db.execute(
                select(ReviewComment)
                .where(ReviewComment.id.in_(comment_ids))
                .order_by(ReviewComment.created_at.asc())
            )).scalars().all()

        # 2. 选 participants
        participants = self._select_participants(group, comments)

        # 3. 写议题
        topic = await self._render_topic(db, group, comments)

        # 4. 创建 DiscussionSession
        session = DiscussionSession(
            project_id=group.project_id,
            topic=topic,
            participants=participants,
            status="running",  # 等待 P4 worker 跑 participant + synthesis
        )
        db.add(session)
        await db.flush()

        # 5. 写 1 条占位 turn (kind='meta', 说明桥接来源)
        meta_turn = DiscussionTurn(
            session_id=session.id,
            turn_no=0,  # 0 = meta, 真实 turn 从 1 开始 (跟 discussion router 约定)
            agent_name="DiscussionBridge",
            role_label="桥接占位",
            kind="meta",
            content=(
                f"本场讨论由 ReviewCommentGroup #{group.id} 自动触发. "
                f"评论数={len(comments)}, severity={group.severity}. "
                f"等待 worker 跑 5 个 participant + chief_synthesis."
            ),
            parsed={
                "source_group_id": group.id,
                "comment_ids": [c.id for c in comments],
                "severity": group.severity,
                "triggered_at": datetime.utcnow().isoformat(),
            },
            error=None,
        )
        db.add(meta_turn)
        await db.flush()

        # 6. 回填 group
        group.discussion_session_id = session.id
        group.status = "discussing"

        # 7. 入队 comment_discussion 任务 (P4 worker 接)
        task = AgentTask(
            project_id=group.project_id,
            task_type="comment_discussion",
            status="pending",
            payload={
                "session_id": session.id,
                "group_id": group.id,
                "chapter_id": group.chapter_id,
                "participants": participants,
            },
            priority=70,  # 高于 reader_review, 低于 user-initiated
        )
        db.add(task)

        logger.info(
            "discussion_bridge: group=%s → session=%s participants=%s "
            "task_id_queued=pending",
            group.id, session.id, participants,
        )
        return session

    # ----- helpers -----

    def _select_participants(
        self,
        group: ReviewCommentGroup,
        comments: list[ReviewComment],
    ) -> list[str]:
        """按 group.severity + 评论 tag 选参与者, 取并集按 spec 顺序去重."""
        picked: list[str] = []
        seen: set[str] = set()

        def _add(items: list[str]) -> None:
            for k in items:
                if k not in seen:
                    seen.add(k)
                    picked.append(k)

        # 1. severity 默认
        sev = (group.severity or "medium").lower()
        _add(SEVERITY_DEFAULT_PARTICIPANTS.get(sev, FALLBACK_PARTICIPANTS))

        # 2. tag 命中 (从评论 tags)
        all_tags: set[str] = set()
        for c in comments:
            for t in c.tags or []:
                all_tags.add(t)
        for tag in all_tags:
            tag_picked = TAG_PARTICIPANT_MAP.get(tag)
            if tag_picked:
                _add(tag_picked)

        if not picked:
            return list(FALLBACK_PARTICIPANTS)
        return picked

    async def _render_topic(
        self,
        db: AsyncSession,
        group: ReviewCommentGroup,
        comments: list[ReviewComment],
    ) -> str:
        """P6 spec §4.4 议题格式:
        来源: 评论区自动生成
        对象: <project> / 第 N 章《<title>》/ 终稿 v<n>
        关联评论: ...
        请讨论: ...
        """
        # 项目
        proj = await db.get(Project, group.project_id) if group.project_id else None
        proj_label = (
            f"#{proj.id} {proj.name}" if proj else f"项目 #{group.project_id}"
        )

        # 章节
        chap_label = "全书"
        ver_label = "终稿"
        if group.chapter_id is not None:
            chap = await db.get(Chapter, group.chapter_id)
            if chap is not None:
                chap_label = f"第{chap.chapter_no}章《{chap.title}》" if chap.title else f"第{chap.chapter_no}章"
        if group.chapter_version_id is not None:
            ver = await db.get(ChapterVersion, group.chapter_version_id)
            if ver is not None:
                ver_label = f"v{ver.version_no}"

        # 关联评论 (前 5 条, 多了就只显示头 5 + count)
        related_lines: list[str] = []
        for i, c in enumerate(comments[:5], start=1):
            label = c.author_label or c.author_type
            snippet = (c.content or "").strip()
            if len(snippet) > 80:
                snippet = snippet[:77] + "..."
            related_lines.append(f"{i}. [{c.author_type}] {label}: {snippet}")
        if len(comments) > 5:
            related_lines.append(f"... 共 {len(comments)} 条评论, 详见 ReviewCommentGroup #{group.id}")

        related_block = "\n".join(related_lines) if related_lines else "(无关联评论)"

        topic = (
            f"来源: 评论区自动生成\n"
            f"对象: {proj_label} / {chap_label} / {ver_label}\n\n"
            f"摘要: {group.summary or group.title}\n"
            f"严重度: {group.severity}\n\n"
            f"关联评论:\n{related_block}\n\n"
            f"请讨论:\n"
            f"- 是否值得修改?\n"
            f"- 轻修、局部返工, 还是大返工?\n"
            f"- 具体修改位置在哪里?\n"
            f"- 修改后如何验证 (复评哪几个读者 Agent)?"
        )
        return topic


_bridge_singleton: DiscussionBridge | None = None


def get_discussion_bridge() -> DiscussionBridge:
    global _bridge_singleton
    if _bridge_singleton is None:
        _bridge_singleton = DiscussionBridge()
    return _bridge_singleton
