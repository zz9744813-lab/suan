"""Seed default prompt templates, model role defaults, and a singleton worker status row."""
from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, init_db
from app.models.agent_role import AgentModelBinding, AgentPromptBinding, AgentRole
from app.models.comment_review import (
    ReaderAgentProfile,
    ReviewSettings,
)
from app.models.model_provider import ModelProvider, ModelRoleAssignment
from app.models.prompt import PromptTemplate, PromptVersion
from app.models.project import Project
from app.models.task import WorkerStatus
from app.prompts.default import WRITING_PROMPTS


# P4 §10 — 11 个默认 AgentRole. 矩阵默认显示前 9 个, 后 3 个
# 折叠到"更多". P4 这一轮 visible_in_matrix 全部 True, 后续
# Matrix UI 内部按 category 分组 (writing/study/memory/discussion).
DEFAULT_AGENT_ROLES: list[dict] = [
    # 写作 5 件套 (P4 §10 矩阵默认显示)
    {"key": "planner",     "display_name": "Planner",     "description": "章节规划 — 主设定 + 大纲 + StableMemory + 伏笔 → chapter_plan",
     "category": "writing", "avatar_style": "scribe",      "run_mode": "pipeline",
     "pipeline_stage": "plan"},
    {"key": "drafter",     "display_name": "Drafter",     "description": "主笔 — chapter_plan + scene beats → 章节正文",
     "category": "writing", "avatar_style": "scribe",      "run_mode": "pipeline",
     "pipeline_stage": "draft"},
    {"key": "critic",      "display_name": "Critic",      "description": "审稿 — 维度打分 + 改写建议",
     "category": "writing", "avatar_style": "critic",      "run_mode": "pipeline",
     "pipeline_stage": "review"},
    {"key": "rewriter",    "display_name": "Rewriter",    "description": "改写 — 采纳 critic 建议生成 rewrite_N",
     "category": "writing", "avatar_style": "scribe",      "run_mode": "pipeline",
     "pipeline_stage": "rewrite"},
    {"key": "continuity",  "display_name": "Continuity",  "description": "连戏 — 状态对账 + 一致性",
     "category": "writing", "avatar_style": "memory_core", "run_mode": "pipeline",
     "pipeline_stage": "continuity"},
    # 记忆类 (P4 §10 矩阵默认显示)
    {"key": "memory_update","display_name": "Memory",     "description": "MemoryUpdate — 章节写完后写 RawMemoryEntry",
     "category": "memory",  "avatar_style": "memory_core", "run_mode": "pipeline",
     "pipeline_stage": "memory_update"},
    # 拆书类 (P4 §10 矩阵默认显示)
    {"key": "deep_study",  "display_name": "DeepStudy",   "description": "DeepStudyCoordinator — 8 子 Agent 流水线",
     "category": "study",   "avatar_style": "study_core",  "run_mode": "manual"},
    # 讨论类 (P4 §10 矩阵默认显示)
    {"key": "discussion",  "display_name": "Discussion",  "description": "DiscussionAgent — 5 角色讨论室 + 裁决",
     "category": "discussion", "avatar_style": "discussion_core", "run_mode": "manual"},
    # 高级 (P4 §10 折叠到"更多")
    {"key": "memory_consolidator", "display_name": "MemoryConsolidator",
     "description": "MemoryConsolidator — 二次加工 (去重 / 合并 / 冲突识别)",
     "category": "memory",  "avatar_style": "memory_core", "run_mode": "manual"},
    {"key": "technique_distill",   "display_name": "TechniqueDistill",
     "description": "TechniqueDistill — 拆书写作技巧蒸馏",
     "category": "study",   "avatar_style": "study_core",  "run_mode": "manual"},
    {"key": "study_critic",        "display_name": "StudyCritic",
     "description": "StudyCritic — 知识密度打分",
     "category": "study",   "avatar_style": "critic",      "run_mode": "manual"},
    # P6: 5 个模拟读者 Agent + 1 个主 Agent 评论接入官
    # 读者 Agent: run_mode="event" (章节完成/手动触发),
    #              pipeline_stage="reader_review" 走 ReaderReviewRun 元数据
    # 评论接入官: run_mode="event" (评论流触发), pipeline_stage="comment_triage"
    {"key": "reader_hook",      "display_name": "Reader·钩子",
     "description": "模拟读者·节奏钩子评审 — 钩子/爆点/章末悬念",
     "category": "review",  "avatar_style": "reader",      "run_mode": "event",
     "pipeline_stage": "reader_review"},
    {"key": "reader_emotion",   "display_name": "Reader·情绪",
     "description": "模拟读者·人物情绪评审 — 动机/情绪递进/共情",
     "category": "review",  "avatar_style": "reader",      "run_mode": "event",
     "pipeline_stage": "reader_review"},
    {"key": "reader_logic",     "display_name": "Reader·逻辑",
     "description": "模拟读者·逻辑设定评审 — 因果/时间线/世界规则",
     "category": "review",  "avatar_style": "reader",      "run_mode": "event",
     "pipeline_stage": "reader_review"},
    {"key": "reader_commercial","display_name": "Reader·商业",
     "description": "模拟读者·商业留存评审 — 付费点/留存/章末钩子",
     "category": "review",  "avatar_style": "reader",      "run_mode": "event",
     "pipeline_stage": "reader_review"},
    {"key": "reader_toxic",     "display_name": "Reader·毒点",
     "description": "模拟读者·毒点劝退评审 — 违和/解释腔/劝退点",
     "category": "review",  "avatar_style": "reader",      "run_mode": "event",
     "pipeline_stage": "reader_review"},
    {"key": "chief_comment_moderator", "display_name": "Chief·评论接入官",
     "description": "主 Agent·评论接入官 — 分流/合并/转讨论/裁决",
     "category": "discussion", "avatar_style": "discussion_core", "run_mode": "event",
     "pipeline_stage": "comment_triage"},
]


DEFAULT_ROLE_ASSIGNMENTS: list[tuple[str, str, str, float, int]] = [
    # role, provider_name, model, temperature, max_tokens
    ("Chief", "stub", "stub-fast", 0.6, 1500),
    ("Planner", "stub", "stub-fast", 0.7, 1500),
    ("Draft", "stub", "stub-fast", 0.9, 4000),
    ("Critic", "stub", "stub-fast", 0.4, 1500),
    ("Rewrite", "stub", "stub-fast", 0.7, 4000),
    ("Continuity", "stub", "stub-fast", 0.3, 1200),
    ("MemoryUpdate", "stub", "stub-fast", 0.2, 1500),
    ("Learning", "stub", "stub-fast", 0.4, 1200),
    # R21: the Study (拆书) agents — StudyCharacterAgent /
    # StudyEventAgent / StudyBehaviorPatternAgent — all share the
    # ``role='StudyAgent'`` label, so one seed entry covers all
    # three. Without an explicit binding, ``LLMRouter.resolve``
    # falls back to the first enabled provider; if that provider
    # is the built-in stub (``mock://local``) the StudyCharacter
    # call would return the canned ``_MOCK_STUDY`` envelope
    # (book_title / world_rules / character_archetypes) which has
    # the WRONG JSON shape and silently 0's the user. The
    # router-level fix in ``app/services/llm/router.py`` now
    # refuses to fall through to ``mock://``, but seeding this row
    # keeps the no-network demo path consistent with the other
    # roles — the user can rebind to a real provider from the UI.
    ("StudyAgent", "stub", "stub-fast", 0.0, 2500),
]


async def seed() -> None:
    await init_db()
    async with AsyncSessionLocal() as db:
        # 1. Prompts
        for key, spec in WRITING_PROMPTS.items():
            tpl = (
                await db.execute(
                    select(PromptTemplate).where(PromptTemplate.template_key == key)
                )
            ).scalar_one_or_none()
            if tpl is None:
                tpl = PromptTemplate(
                    template_key=key,
                    name=spec["name"],
                    category=spec["category"],
                    role=spec["role"],
                    scope=spec["scope"],
                    genre=spec.get("genre"),
                    description=spec.get("description"),
                    allowed_inputs=spec.get("allowed_inputs", []),
                    forbidden_inputs=spec.get("forbidden_inputs", []),
                    output_schema=spec.get("output_schema"),
                    can_modify=spec.get("can_modify", []),
                    cannot_modify=spec.get("cannot_modify", []),
                    hard_rules=spec.get("hard_rules", []),
                )
                db.add(tpl)
                await db.flush()
            else:
                # R15 / Plan A: keep the template's metadata in sync with the
                # library spec on every seed run. Without this, allowed_inputs
                # and hard_rules on existing rows never update — the body
                # gets auto-bumped (see below) but the UI version viewer
                # keeps showing the old metadata. This 8-line sync makes the
                # whole template self-healing.
                tpl.name = spec["name"]
                tpl.category = spec["category"]
                tpl.role = spec["role"]
                tpl.scope = spec["scope"]
                tpl.genre = spec.get("genre")
                tpl.description = spec.get("description")
                tpl.allowed_inputs = spec.get("allowed_inputs", [])
                tpl.forbidden_inputs = spec.get("forbidden_inputs", [])
                tpl.output_schema = spec.get("output_schema")
                tpl.can_modify = spec.get("can_modify", [])
                tpl.cannot_modify = spec.get("cannot_modify", [])
                tpl.hard_rules = spec.get("hard_rules", [])
            # ensure v1 exists
            existing = (
                await db.execute(
                    select(PromptVersion).where(PromptVersion.template_id == tpl.id)
                )
            ).scalars().all()
            if not existing:
                ver = PromptVersion(
                    template_id=tpl.id, version=1, body=spec["body"],
                    status="active", change_note="initial seed",
                )
                db.add(ver)
                await db.flush()
                tpl.active_version_id = ver.id
            else:
                # Auto-bump: if the library body diverges from the active
                # version, snapshot a new version and switch the template
                # over. This lets code-side prompt tweaks propagate via
                # ``python -m app.seed`` without a manual "save new
                # version" dance. Existing v1 is preserved as deprecated
                # so the history page still shows the diff.
                active = next(
                    (v for v in existing if v.id == tpl.active_version_id),
                    next((v for v in existing if v.status == "active"), existing[0]),
                )
                if active and active.body != spec["body"]:
                    next_no = max(v.version for v in existing) + 1
                    # Demote current active to deprecated
                    active.status = "deprecated"
                    ver = PromptVersion(
                        template_id=tpl.id, version=next_no, body=spec["body"],
                        status="active",
                        change_note="auto-bump by seed: library body changed",
                    )
                    db.add(ver)
                    await db.flush()
                    tpl.active_version_id = ver.id

        # 2. A built-in stub provider so the system works out of the box.
        #    Uses the in-process mock LLM (`mock://`) so the UI and pipeline
        #    are runnable without any external API key. Users can later add a
        #    real provider and rebind roles in the "模型配置" page.
        stub = (
            await db.execute(
                select(ModelProvider).where(ModelProvider.name == "stub")
            )
        ).scalar_one_or_none()
        if stub is None:
            stub = ModelProvider(
                name="stub",
                base_url="mock://local",
                api_key="mock",
                default_model="mock-fast",
                model_list=["mock-fast", "mock-long", "mock-vision"],
                enabled=True,
                extra={"note": "Local mock LLM. Replace with a real OpenAI-compatible provider when ready."},
            )
            db.add(stub)
            await db.flush()
        else:
            # Upgrade old broken stub: switch to mock:// and enable it.
            if stub.base_url != "mock://local" or not stub.enabled:
                stub.base_url = "mock://local"
                stub.api_key = "mock"
                stub.default_model = stub.default_model or "mock-fast"
                stub.enabled = True
        # 3. Default role assignments
        for role, prov_name, model, temp, maxtok in DEFAULT_ROLE_ASSIGNMENTS:
            existing = (
                await db.execute(
                    select(ModelRoleAssignment).where(ModelRoleAssignment.role == role)
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(ModelRoleAssignment(
                    role=role, provider_id=stub.id, model=model,
                    temperature=temp, max_tokens=maxtok,
                    notes="default seed; please rebind to a real provider",
                ))

        # 4. WorkerStatus singleton
        ws = await db.get(WorkerStatus, 1)
        if ws is None:
            db.add(WorkerStatus(id=1, state="idle"))

        # 5. P4: 默认 AgentRole + 默认 AgentModelBinding (走 stub)
        #    P4 这一轮不创建 AgentPromptBinding (跟现有 11 个角色保持一致),
        #    角色硬编码 prompt_key 在调用处解析.
        for spec in DEFAULT_AGENT_ROLES:
            row = (await db.execute(
                select(AgentRole).where(AgentRole.key == spec["key"])
            )).scalar_one_or_none()
            if row is None:
                row = AgentRole(**spec)
                db.add(row)
                await db.flush()
                # 默认 model binding: 走 stub provider
                db.add(AgentModelBinding(
                    agent_role_id=row.id,
                    provider_id=stub.id,
                    model_name="mock-fast",
                ))

        # 6. P6: 5 个 ReaderAgentProfile (跟 5 个 reader AgentRole 1:1)
        #    维度跟 reader_key 对应, weight 初始 1.0, enabled=True
        READER_PROFILES: list[tuple[str, str, str]] = [
            ("reader_hook",       "Reader·钩子",   "节奏/钩子/爆点"),
            ("reader_emotion",    "Reader·情绪",   "人物动机/情绪递进"),
            ("reader_logic",      "Reader·逻辑",   "设定硬伤/因果/行为合理性"),
            ("reader_commercial", "Reader·商业",   "留存/付费点/章末钩子"),
            ("reader_toxic",      "Reader·毒点",   "劝退点/违和/解释腔"),
        ]
        for reader_key, display_name, dimension in READER_PROFILES:
            # 通过 key 找 AgentRole
            role_row = (await db.execute(
                select(AgentRole).where(AgentRole.key == reader_key)
            )).scalar_one_or_none()
            if role_row is None:
                continue  # 上一步没创建成功, 跳过
            existing_profile = (await db.execute(
                select(ReaderAgentProfile).where(
                    ReaderAgentProfile.reader_key == reader_key
                )
            )).scalar_one_or_none()
            if existing_profile is None:
                db.add(ReaderAgentProfile(
                    agent_role_id=role_row.id,
                    reader_key=reader_key,
                    display_name=display_name,
                    dimension=dimension,
                    weight=1.0,
                    adopted_count=0,
                    rejected_count=0,
                    generated_comment_count=0,
                    enabled=True,
                ))

        # 7. P6: 每个 project 一行 ReviewSettings (1:1 with Project)
        #    默认 auto 全部开启, retention 7 天
        projects = (await db.execute(select(Project))).scalars().all()
        for proj in projects:
            existing_settings = (await db.execute(
                select(ReviewSettings).where(ReviewSettings.project_id == proj.id)
            )).scalar_one_or_none()
            if existing_settings is None:
                db.add(ReviewSettings(
                    project_id=proj.id,
                    auto_reader_review=True,
                    auto_chief_triage=True,
                    auto_discussion=True,
                    retention_days=7,
                    max_comments_per_chapter=50,
                    max_reader_comments_per_run=5,
                    min_severity_for_discussion="medium",
                ))

        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed())
    print("Seed complete.")
