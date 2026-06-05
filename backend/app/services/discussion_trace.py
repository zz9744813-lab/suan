"""P9: Discussion Auto-Trace — Services

IssueDetectorService: 接收 Critic/Reader/Continuity 结果，自动创建讨论线程
SkillBuilderService: 从讨论内容和 Chief 结论中提炼 Skill 草案
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discussion_trace import (
    DiscussionIssueSource,
    DiscussionSkillDraft,
    DiscussionThread,
    Skill,
)


# ===========================================================================
# IssueDetectorService
# ===========================================================================

class IssueDetectorService:
    """接收 Critic / Reader / Continuity 结果，自动创建讨论线程。"""

    RECYCLE_DAYS = 7

    async def detect_from_critic_result(
        self,
        db: AsyncSession,
        project_id: int,
        chapter_id: int | None,
        task_id: int | None,
        critic_result: dict,
    ) -> DiscussionThread | None:
        """Critic 低分自动创建讨论。"""
        scores = critic_result.get("scores", {})
        total = scores.get("total", 100)
        logic = scores.get("logic", 100)
        character = scores.get("character", 100)
        hook = scores.get("commercial_hook", 100)
        style = scores.get("style", 100)

        issues: list[tuple[str, str, str]] = []  # (title, issue_type, risk_level)
        if total < 70:
            issues.append((f"章节评分过低 ({total}分)", "quality", "high"))
        if logic < 75:
            issues.append((f"逻辑评分过低 ({logic}分)", "logic", "high"))
        if character < 75:
            issues.append((f"人物评分过低 ({character}分)", "character", "medium"))
        if hook < 70:
            issues.append((f"爽点评分过低 ({hook}分)", "commercial_hook", "high"))
        if style < 70:
            issues.append((f"文风评分过低 ({style}分)", "style", "medium"))

        if not issues:
            return None

        # 取最严重的那个
        title, issue_type, risk_level = issues[0]
        summary = critic_result.get("summary", "")[:500]

        return await self._create_thread_if_needed(
            db=db,
            project_id=project_id,
            chapter_id=chapter_id,
            task_id=task_id,
            title=title,
            issue_type=issue_type,
            risk_level=risk_level,
            source_type="critic",
            source_agent_role="critic",
            problem_summary=summary,
            severity=risk_level,
            payload=critic_result,
        )

    async def detect_from_continuity_result(
        self,
        db: AsyncSession,
        project_id: int,
        chapter_id: int | None,
        continuity_result: dict,
    ) -> DiscussionThread | None:
        """Continuity 检测到问题自动创建讨论。"""
        issues = continuity_result.get("issues", [])
        if not issues:
            return None

        worst = issues[0]
        issue_type_map = {
            "setting_conflict": "continuity",
            "foreshadow_overdue": "foreshadowing",
            "character_state_conflict": "character",
            "timeline_conflict": "continuity",
            "prop_missing": "continuity",
        }
        issue_type = issue_type_map.get(worst.get("type", ""), "continuity")
        risk_map = {"critical": "critical", "high": "high", "medium": "medium", "low": "low"}
        risk_level = risk_map.get(worst.get("severity", "medium"), "medium")

        title = worst.get("title", "连续性问题")[:200]
        summary = worst.get("description", "")[:500]

        return await self._create_thread_if_needed(
            db=db,
            project_id=project_id,
            chapter_id=chapter_id,
            task_id=None,
            title=title,
            issue_type=issue_type,
            risk_level=risk_level,
            source_type="continuity",
            source_agent_role="continuity",
            problem_summary=summary,
            severity=risk_level,
            payload=worst,
        )

    async def detect_from_reader_feedback(
        self,
        db: AsyncSession,
        project_id: int,
        chapter_id: int | None,
        feedback_batch: list[dict],
    ) -> DiscussionThread | None:
        """Reader 反馈触发。"""
        # 简单统计：如果多数读者有负面反馈则触发
        negative = [f for f in feedback_batch if f.get("sentiment") == "negative"]
        if len(negative) < max(2, len(feedback_batch) * 0.4):
            return None

        issue_type_map = {
            "want_drop": "pacing",
            "confused": "logic",
            "character_inconsistent": "character",
            "no_emotion": "commercial_hook",
            "not_satisfying": "commercial_hook",
        }
        # 统计最常见的负面类型
        from collections import Counter
        type_counts = Counter(f.get("feedback_type", "other") for f in negative)
        most_common = type_counts.most_common(1)[0][0] if type_counts else "other"
        issue_type = issue_type_map.get(most_common, "other")

        title = f"读者反馈：{most_common} ({len(negative)}/{len(feedback_batch)}条负面)"
        summary = " | ".join(f.get("comment", "")[:100] for f in negative[:3])

        return await self._create_thread_if_needed(
            db=db,
            project_id=project_id,
            chapter_id=chapter_id,
            task_id=None,
            title=title,
            issue_type=issue_type,
            risk_level="medium",
            source_type="reader",
            source_agent_role="reader",
            problem_summary=summary[:500],
            severity="medium",
            payload={"negative_count": len(negative), "total": len(feedback_batch)},
        )

    async def _create_thread_if_needed(
        self,
        db: AsyncSession,
        project_id: int,
        chapter_id: int | None,
        task_id: int | None,
        title: str,
        issue_type: str,
        risk_level: str,
        source_type: str,
        source_agent_role: str | None,
        problem_summary: str,
        severity: str = "medium",
        payload: dict | None = None,
    ) -> DiscussionThread | None:
        """创建讨论线程（去重）。"""
        fingerprint = self.build_issue_fingerprint(project_id, chapter_id, issue_type, problem_summary)

        # 检查 7 天内是否已有同 fingerprint 且未回收
        existing = (await db.execute(
            select(DiscussionThread).where(
                DiscussionThread.issue_fingerprint == fingerprint,
                DiscussionThread.status != "recycled",
                DiscussionThread.created_at >= datetime.utcnow() - timedelta(days=7),
            )
        )).scalar_one_or_none()

        if existing:
            # 追加证据
            db.add(DiscussionIssueSource(
                thread_id=existing.id,
                source_type=source_type,
                chapter_id=chapter_id,
                problem_summary=problem_summary,
                severity=severity,
                payload_json=payload,
            ))
            await db.flush()
            # 可升级风险
            risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
            if risk_order.get(risk_level, 0) > risk_order.get(existing.risk_level, 0):
                existing.risk_level = risk_level
            return existing

        # 创建新线程
        now = datetime.utcnow()
        thread = DiscussionThread(
            project_id=project_id,
            chapter_id=chapter_id,
            task_id=task_id,
            title=title,
            source_type=source_type,
            source_agent_role=source_agent_role,
            issue_type=issue_type,
            risk_level=risk_level,
            status="pending_discussion",
            recycle_at=now + timedelta(days=self.RECYCLE_DAYS),
            issue_fingerprint=fingerprint,
        )
        db.add(thread)
        await db.flush()

        # 创建问题来源
        db.add(DiscussionIssueSource(
            thread_id=thread.id,
            source_type=source_type,
            chapter_id=chapter_id,
            problem_summary=problem_summary,
            severity=severity,
            payload_json=payload,
        ))
        await db.flush()

        return thread

    @staticmethod
    def build_issue_fingerprint(
        project_id: int,
        chapter_id: int | None,
        issue_type: str,
        problem_summary: str,
    ) -> str:
        """生成去重指纹。"""
        normalized = problem_summary.strip().lower()[:200]
        raw = f"{project_id}:{chapter_id}:{issue_type}:{normalized}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ===========================================================================
# SkillBuilderService
# ===========================================================================

class SkillBuilderService:
    """从讨论内容和 Chief 结论中提炼 Skill 草案。"""

    async def create_skill_draft_from_thread(
        self,
        db: AsyncSession,
        thread_id: int,
        skill_data: dict,
    ) -> DiscussionSkillDraft:
        """根据 Chief 输出的 skill_candidate 创建草案。"""
        thread = await db.get(DiscussionThread, thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")

        draft = DiscussionSkillDraft(
            thread_id=thread_id,
            project_id=thread.project_id or 0,
            title=skill_data.get("title", f"Skill from thread #{thread_id}"),
            skill_type=skill_data.get("skill_type", "character_rewrite"),
            status="draft",
            trigger_conditions_json=skill_data.get("trigger_conditions", []),
            applicable_scenes_json=skill_data.get("applicable_scenes", []),
            anti_patterns_json=skill_data.get("anti_patterns", []),
            execution_template=skill_data.get("execution_template", ""),
            prompt_snippet=skill_data.get("prompt_snippet"),
            applicable_agent_roles_json=skill_data.get("applicable_agent_roles", []),
            source_summary=skill_data.get("source_summary"),
            source_thread_summary=thread.summary,
            quality_score=skill_data.get("quality_score", 0.0),
        )
        db.add(draft)
        await db.flush()

        # 更新线程
        thread.skill_draft_id = draft.id
        if thread.status in ("converged", "rewrite_created"):
            thread.status = "skill_draft_created"
        thread.updated_at = datetime.utcnow()
        await db.flush()

        return draft

    async def solidify_skill_draft(
        self,
        db: AsyncSession,
        draft_id: int,
    ) -> Skill:
        """固化 Skill 草案为正式 Skill。"""
        draft = await db.get(DiscussionSkillDraft, draft_id)
        if not draft:
            raise ValueError(f"SkillDraft {draft_id} not found")

        skill = Skill(
            title=draft.title,
            skill_type=draft.skill_type,
            trigger_conditions_json=draft.trigger_conditions_json or [],
            applicable_scenes_json=draft.applicable_scenes_json or [],
            anti_patterns_json=draft.anti_patterns_json or [],
            execution_template=draft.execution_template,
            prompt_snippet=draft.prompt_snippet,
            applicable_agent_roles_json=draft.applicable_agent_roles_json or [],
            source_type="discussion",
            source_thread_id=draft.thread_id,
            quality_score=draft.quality_score,
        )
        db.add(skill)
        await db.flush()

        draft.status = "solidified"
        draft.solidified_at = datetime.utcnow()
        draft.solidified_skill_id = skill.id
        await db.flush()

        return skill

    async def reject_skill_draft(
        self,
        db: AsyncSession,
        draft_id: int,
        reason: str = "",
    ) -> None:
        """拒绝 Skill 草案。"""
        draft = await db.get(DiscussionSkillDraft, draft_id)
        if not draft:
            raise ValueError(f"SkillDraft {draft_id} not found")
        draft.status = "rejected"
        draft.source_summary = (draft.source_summary or "") + f"\n[拒绝原因]: {reason}"
        await db.flush()
