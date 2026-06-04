"""ReaderReviewService: 触发 5 个读者 Agent 评审一章 (P6 §4.2).

入口:
  ReaderReviewService.run_for_chapter(
      db, *, project_id, chapter_id, chapter_version_id, trigger,
  )
  → 返回 ReaderReviewOutcome (run_id, comment_ids, status, error_count, ...)

工作流:
  1. 找 chapter + final version
  2. 查 ReviewSettings (auto_reader_review 开关, retention_days, max_reader_comments_per_run)
  3. 查 enabled ReaderAgentProfile, 按 weight desc
  4. 创建 ReaderReviewRun (status=running, started_at=now)
  5. 对每个 reader:
       a. 准备 inputs (chapter_text / chapter_outline / 上一章摘要 / 角色设定 / 世界设定)
       b. AgentRoleRunner.run(agent_key=reader_key, ...) — 自动写 AgentRun / Event
       c. 解析 parsed.comments[0] (或整个 parsed fallback)
       d. 写 ReviewComment (author_type='reader_agent', status='new', expires_at=+7d)
  6. 更新 ReaderReviewRun (status / token / cost / reader_keys / comment_ids / error)
  7. enqueue comment_triage 任务 (P3 才实现, P2 写 event 占位)

错误处理: 单个 reader 失败不影响其他 reader, ReaderReviewRun.status
按成功 reader 数量分流:
  - 5/5 → succeeded
  - 1..4 → partial
  - 0/5 → failed
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import bad_request, not_found
from app.models.agent_role import AgentRole
from app.models.comment_review import (
    ReaderAgentProfile,
    ReaderReviewRun,
    ReviewComment,
    ReviewSettings,
)
from app.models.project import Chapter, ChapterVersion
from app.services.review.agent_role_runner import AgentRoleRunner, get_agent_role_runner

logger = logging.getLogger(__name__)


# trigger → 哪种事件触发的读者评审 (存到 ReaderReviewRun.trigger)
TRIGGER_CHAPTER_COMPLETED = "chapter_completed"
TRIGGER_REWRITE_COMPLETED = "rewrite_completed"
TRIGGER_MANUAL_TEST = "manual_test"
TRIGGER_SCHEDULED = "scheduled"

VALID_TRIGGERS = frozenset({
    TRIGGER_CHAPTER_COMPLETED,
    TRIGGER_REWRITE_COMPLETED,
    TRIGGER_MANUAL_TEST,
    TRIGGER_SCHEDULED,
})


# AgentRole.key → PromptTemplate.template_key 映射.
# 5 个 reader agent 的 key 比 template_key 短 (reader_hook vs
# reader_hook_comment), chief 的 template 是 chief_comment_triage
# (P2 阶段), 留 P3 决定动态选 triage / reply / decision.
_AGENT_KEY_TO_TEMPLATE_KEY: dict[str, str] = {
    "reader_hook": "reader_hook_comment",
    "reader_emotion": "reader_emotion_comment",
    "reader_logic": "reader_logic_comment",
    "reader_commercial": "reader_commercial_comment",
    "reader_toxic": "reader_toxic_comment",
    "chief_comment_moderator": "chief_comment_triage",
}


@dataclass
class ReaderReviewOutcome:
    """ReaderReviewService.run_for_chapter 的返回结果."""

    run_id: int
    status: str  # succeeded / partial / failed
    chapter_id: int
    chapter_version_id: int | None
    reader_keys_attempted: list[str] = field(default_factory=list)
    reader_keys_succeeded: list[str] = field(default_factory=list)
    reader_keys_failed: list[str] = field(default_factory=list)
    comment_ids: list[int] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    error: str | None = None


class ReaderReviewService:
    def __init__(self, runner: AgentRoleRunner | None = None) -> None:
        self.runner = runner or get_agent_role_runner()

    async def run_for_chapter(
        self,
        db: AsyncSession,
        *,
        project_id: int,
        chapter_id: int,
        chapter_version_id: int | None = None,
        trigger: str = TRIGGER_MANUAL_TEST,
    ) -> ReaderReviewOutcome:
        if trigger not in VALID_TRIGGERS:
            raise bad_request(f"Invalid trigger '{trigger}'", suggestion=f"Use one of {sorted(VALID_TRIGGERS)}")

        # 1. Chapter
        chapter = await db.get(Chapter, chapter_id)
        if chapter is None or chapter.project_id != project_id:
            raise not_found("Chapter", f"id={chapter_id} project_id={project_id}")

        # 2. ReviewSettings
        settings = (
            await db.execute(
                select(ReviewSettings).where(ReviewSettings.project_id == project_id)
            )
        ).scalar_one_or_none()
        if settings is None:
            # 兜底: 没 seed 到 (P6 不会发生, 但容错)
            settings = ReviewSettings(project_id=project_id)
            db.add(settings)
            await db.flush()
        if not settings.auto_reader_review and trigger != TRIGGER_MANUAL_TEST:
            raise bad_request(
                f"项目 {project_id} 的 auto_reader_review 已关闭, 拒绝自动触发",
                suggestion="如需强制触发, 使用 trigger=manual_test",
            )

        # 3. Final version (优先 explicit, 否则 latest final/draft)
        version = await self._resolve_version(db, chapter, chapter_version_id)
        if version is None or not version.content:
            raise bad_request(
                f"Chapter {chapter_id} 没有可评审的版本",
                suggestion="需要先有终稿 / draft / rewrite 内容",
            )

        # 4. ReaderAgentProfile (enabled, 按 weight desc)
        profiles = (
            await db.execute(
                select(ReaderAgentProfile)
                .where(ReaderAgentProfile.enabled.is_(True))
                .order_by(ReaderAgentProfile.weight.desc(), ReaderAgentProfile.id.asc())
            )
        ).scalars().all()
        if not profiles:
            raise bad_request(
                f"项目 {project_id} 没有任何启用的读者 Agent (ReaderAgentProfile.enabled=1)",
            )

        max_per_run = max(1, settings.max_reader_comments_per_run)
        profiles = profiles[:max_per_run]

        # 5. Inputs
        inputs = await self._build_inputs(db, chapter, version)

        # 6. Create ReaderReviewRun
        retention = max(1, settings.retention_days)
        run = ReaderReviewRun(
            project_id=project_id,
            chapter_id=chapter_id,
            chapter_version_id=version.id,
            trigger=trigger,
            status="running",
            reader_agent_keys=[p.reader_key for p in profiles],
            generated_comment_ids=[],
            started_at=datetime.utcnow(),
        )
        db.add(run)
        await db.flush()
        run_id = run.id

        outcome = ReaderReviewOutcome(
            run_id=run_id,
            status="running",
            chapter_id=chapter_id,
            chapter_version_id=version.id,
            reader_keys_attempted=[p.reader_key for p in profiles],
        )

        # 7. Fan-out
        generated_ids: list[int] = []
        failed_keys: list[str] = []
        for profile in profiles:
            try:
                comment = await self._run_one_reader(
                    db,
                    run=run,
                    profile=profile,
                    chapter=chapter,
                    version=version,
                    inputs=inputs,
                    retention_days=retention,
                )
                if comment is not None:
                    generated_ids.append(comment.id)
                    outcome.reader_keys_succeeded.append(profile.reader_key)
                else:
                    failed_keys.append(profile.reader_key)
            except Exception as exc:
                logger.exception(
                    "reader_review: reader %s failed for chapter %s",
                    profile.reader_key, chapter_id,
                )
                failed_keys.append(profile.reader_key)
                outcome.error = (
                    f"{profile.reader_key}: {type(exc).__name__}: {exc}"
                )

        # 8. Run finalization (token/cost 累加在 _run_one_reader 里 update ReaderReviewRun 总数)
        succeeded_n = len(outcome.reader_keys_succeeded)
        attempted_n = len(profiles)
        if succeeded_n == attempted_n and attempted_n > 0:
            final_status = "succeeded"
        elif succeeded_n == 0:
            final_status = "failed"
        else:
            final_status = "partial"

        run.status = final_status
        run.generated_comment_ids = generated_ids
        run.finished_at = datetime.utcnow()
        if failed_keys:
            # 不覆盖主 error, 拼到末尾
            extra = "; ".join(failed_keys)
            run.error = (outcome.error + " | " if outcome.error else "") + f"failed: {extra}"

        await db.flush()

        outcome.status = final_status
        outcome.comment_ids = generated_ids
        outcome.reader_keys_failed = failed_keys

        logger.info(
            "reader_review: run_id=%s chapter=%s status=%s %d/%d succeeded",
            run_id, chapter_id, final_status, succeeded_n, attempted_n,
        )

        return outcome

    async def _resolve_version(
        self,
        db: AsyncSession,
        chapter: Chapter,
        explicit_version_id: int | None,
    ) -> ChapterVersion | None:
        if explicit_version_id is not None:
            v = await db.get(ChapterVersion, explicit_version_id)
            if v is not None and v.chapter_id == chapter.id:
                return v
        # fallback: 找 final 优先, 否则最新 version
        final = (
            await db.execute(
                select(ChapterVersion)
                .where(ChapterVersion.chapter_id == chapter.id)
                .where(ChapterVersion.version_kind == "final")
                .order_by(ChapterVersion.version_no.desc())
            )
        ).scalars().first()
        if final is not None:
            return final
        any_v = (
            await db.execute(
                select(ChapterVersion)
                .where(ChapterVersion.chapter_id == chapter.id)
                .order_by(ChapterVersion.version_no.desc())
            )
        ).scalars().first()
        return any_v

    async def _build_inputs(
        self,
        db: AsyncSession,
        chapter: Chapter,
        version: ChapterVersion,
    ) -> dict[str, Any]:
        """根据 chapter 上下文, 准备 reader prompts 需要的 inputs.

        当前 P2 只填核心字段 (chapter_text / chapter_outline /
        previous_chapter_summary / character_bible / world_bible), 让
        reader Agent 至少有上下文。P3 接入 ContextCompiler 时复用更
        完整的字段。
        """
        from app.models.project import Outline
        from app.models.memory import MemoryCharacter
        from app.models.memory_v2 import StableMemoryEntity

        inputs: dict[str, Any] = {
            "chapter_text": version.content,
            "chapter_title": chapter.title,
            "chapter_no": chapter.chapter_no,
            "chapter_outline": "",
            "previous_chapter_summary": "",
            "character_bible": "",
            "world_bible": "",
        }

        # Outline
        outline = (
            await db.execute(
                select(Outline).where(Outline.id == chapter.outline_id)
            )
        ).scalar_one_or_none()
        if outline is not None:
            inputs["chapter_outline"] = (
                f"#{outline.chapter_no} {outline.title}\n{outline.summary or ''}"
            )

        # 上一章摘要
        prev_chapter = (
            await db.execute(
                select(Chapter)
                .where(Chapter.project_id == chapter.project_id)
                .where(Chapter.chapter_no < chapter.chapter_no)
                .order_by(Chapter.chapter_no.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if prev_chapter is not None:
            prev_version = (
                await db.execute(
                    select(ChapterVersion)
                    .where(ChapterVersion.chapter_id == prev_chapter.id)
                    .order_by(ChapterVersion.version_no.desc())
                )
            ).scalars().first()
            if prev_version is not None and prev_version.summary:
                inputs["previous_chapter_summary"] = prev_version.summary

        # MemoryCharacter (旧表, 简单拼接)
        chars = (
            await db.execute(
                select(MemoryCharacter).where(MemoryCharacter.project_id == chapter.project_id)
            )
        ).scalars().all()
        if chars:
            char_lines = []
            for c in chars[:20]:
                line = f"- {c.name}"
                if c.role:
                    line += f" ({c.role})"
                # base_profile 是 dict, 拼接里面有意义的字段
                bp = c.base_profile or {}
                desc = ""
                for k in ("description", "background", "personality", "bio", "summary"):
                    v = bp.get(k)
                    if isinstance(v, str) and v.strip():
                        desc = v.strip()[:120]
                        break
                if not desc and c.tags:
                    desc = "tags=" + ",".join(c.tags[:5])
                if desc:
                    line += f": {desc}"
                char_lines.append(line)
            inputs["character_bible"] = "\n".join(char_lines)

        # StableMemoryEntity (P3 表, world_rule + character/location/faction)
        entities = (
            await db.execute(
                select(StableMemoryEntity)
                .where(StableMemoryEntity.project_id == chapter.project_id)
                .where(StableMemoryEntity.entity_type.in_(("world_rule", "character", "location", "faction")))
            )
        ).scalars().all()
        if entities:
            ent_lines = []
            for e in entities[:30]:
                line = f"- [{e.entity_type}] {e.canonical_name}"
                # profile 是 dict, 抽 description 之类的字段
                desc = ""
                if e.profile:
                    for k in ("description", "background", "summary", "rule", "bio"):
                        v = e.profile.get(k)
                        if isinstance(v, str) and v.strip():
                            desc = v.strip()[:120]
                            break
                if desc:
                    line += f": {desc}"
                ent_lines.append(line)
            inputs["world_bible"] = "\n".join(ent_lines)

        return inputs

    async def _run_one_reader(
        self,
        db: AsyncSession,
        *,
        run: ReaderReviewRun,
        profile: ReaderAgentProfile,
        chapter: Chapter,
        version: ChapterVersion,
        inputs: dict[str, Any],
        retention_days: int,
    ) -> ReviewComment | None:
        # 1. 准备 inputs
        reader_inputs = dict(inputs)
        reader_inputs["reader_weight"] = profile.weight
        reader_inputs["reader_dimension"] = profile.dimension
        reader_inputs["reader_display_name"] = profile.display_name

        # agent_key 跟 template_key 命名不一致, 显式映射:
        #   reader_hook → reader_hook_comment
        #   chief_comment_moderator → chief_comment_triage (P2 阶段固定 triage)
        template_key = _AGENT_KEY_TO_TEMPLATE_KEY.get(
            profile.reader_key, profile.reader_key
        )

        result = await self.runner.run(
            db,
            agent_key=profile.reader_key,
            project_id=chapter.project_id,
            task_id=None,
            run_type="reader_review",
            inputs=reader_inputs,
            template_key=template_key,
        )

        # 2. 解析 — 优先 comments[0], 否则整个 parsed 作为单条
        if not result.ok:
            comment_text = (
                f"[解析失败] reader={profile.reader_key} "
                f"error={result.parse_error}\n\n"
                f"原始输出 (前 500 字):\n{result.raw_content[:500]}"
            )
            comment_dict: dict[str, Any] = {
                "summary": f"{profile.display_name} 解析失败",
                "content": comment_text,
                "evidence": [],
                "tags": ["parse_error"],
                "rating": {"score": 0, "dimensions": {}},
                "severity": "low",  # 系统错误, 不算读者意见
                "suggestion": "查看 AgentRunEvent 详情",
            }
        else:
            parsed = result.parsed
            comments_list = parsed.get("comments")
            if isinstance(comments_list, list) and comments_list:
                c0 = comments_list[0]
                if not isinstance(c0, dict):
                    c0 = {"content": str(c0)}
                comment_dict = c0
            else:
                # 整个 parsed 当作单条 (宽松 fallback)
                comment_dict = parsed

        # 3. 标准化字段
        content = str(
            comment_dict.get("content")
            or comment_dict.get("comment_text")
            or comment_dict.get("text")
            or "(无内容)"
        ).strip()
        summary = str(comment_dict.get("summary") or "")[:200].strip()
        evidence = comment_dict.get("evidence")
        if not isinstance(evidence, list):
            evidence = None
        rating = comment_dict.get("rating")
        if not isinstance(rating, dict):
            rating = None
        tags = comment_dict.get("tags")
        if not isinstance(tags, list):
            tags = []
        severity = str(comment_dict.get("severity") or "medium").lower()
        if severity not in ("low", "medium", "high", "blocker"):
            severity = "medium"
        suggestion = str(comment_dict.get("suggestion") or "")[:500].strip()

        # 4. Write ReviewComment
        comment = ReviewComment(
            project_id=chapter.project_id,
            chapter_id=chapter.id,
            chapter_version_id=version.id,
            parent_id=None,
            target_type="chapter",
            author_type="reader_agent",
            author_label=profile.display_name,
            agent_role_id=profile.agent_role_id,
            content=content,
            evidence=evidence,
            rating=rating,
            tags=tags,
            weight_at_created=profile.weight,
            status="new",
            priority=self._severity_to_priority(severity),
            related_group_id=None,
            related_discussion_id=None,
            expires_at=datetime.utcnow() + timedelta(days=retention_days),
        )
        db.add(comment)
        await db.flush()

        # 5. 累加 token / cost
        run.total_input_tokens += result.input_tokens
        run.total_output_tokens += result.output_tokens
        run.total_cost_usd = round(run.total_cost_usd + result.cost_usd, 6)

        # 6. 更新 ReaderAgentProfile
        profile.generated_comment_count = (profile.generated_comment_count or 0) + 1
        profile.last_used_at = datetime.utcnow()

        return comment

    @staticmethod
    def _severity_to_priority(severity: str) -> int:
        # blocker=90, high=75, medium=50, low=25
        return {
            "blocker": 90,
            "high": 75,
            "medium": 50,
            "low": 25,
        }.get(severity, 50)


_service_singleton: ReaderReviewService | None = None


def get_reader_review_service() -> ReaderReviewService:
    global _service_singleton
    if _service_singleton is None:
        _service_singleton = ReaderReviewService()
    return _service_singleton
