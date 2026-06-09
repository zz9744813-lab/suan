"""Seed default prompt templates, model role defaults, and a singleton worker status row."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal, init_db
from app.models.agent_role import AgentModelBinding, AgentPromptBinding, AgentRole
from app.models.comment_review import (
    ReaderAgentProfile,
    ReviewSettings,
)
from app.models.model_provider import ModelProvider, ModelRoleAssignment
from app.models.prompt import PromptTemplate, PromptVersion
from app.models.genre_prompt_map import GenrePromptMapping
from app.models.agent_memory import AgentMemoryEntry
from app.models.project import Project
from app.models.task import WorkerStatus
from app.prompts.default import WRITING_PROMPTS
from app.prompts.default.library import GENRE_PROMPTS


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
                    immutable=True,  # seed templates can't be deleted
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

        # 2. 默认 Provider: 禁止创建 mock/stub。
        #    没有真实 Provider 时，Agent 保持未绑定，运行时显式失败并提示配置真实模型。
        real_provider = (
            await db.execute(
                select(ModelProvider).where(
                    ModelProvider.enabled == True,  # noqa: E712
                    ModelProvider.base_url.notlike("mock://%"),
                    ModelProvider.name.notin_(["stub", "mock"]),
                ).order_by(ModelProvider.id)
            )
        ).scalar_one_or_none()
        stub_rows = (await db.execute(
            select(ModelProvider).where(
                (ModelProvider.base_url.like("mock://%")) | (ModelProvider.name.in_(["stub", "mock"]))
            )
        )).scalars().all()
        for stub in stub_rows:
            stub.enabled = False
            stub.circuit_state = "open"
            stub.last_failure_type = "disabled_mock_provider"
            stub.last_failure_message = "mock/stub provider is disabled by production policy"

        # 3. Default role assignments: 只在存在真实 Provider 时补齐旧表默认绑定。
        for role, prov_name, model, temp, maxtok in DEFAULT_ROLE_ASSIGNMENTS:
            if real_provider is None:
                break
            existing = (
                await db.execute(
                    select(ModelRoleAssignment).where(ModelRoleAssignment.role == role)
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(ModelRoleAssignment(
                    role=role, provider_id=real_provider.id, model=real_provider.default_model or (real_provider.model_list or [model])[0],
                    temperature=temp, max_tokens=maxtok,
                    notes="default seed; bound to first real provider",
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
            # 默认 model binding: 只绑定真实 Provider；没有真实 Provider 时保持未绑定。
            # Idempotent: AgentModelBinding.agent_role_id UNIQUE, 只在缺时创建
            existing_binding = (await db.execute(
                select(AgentModelBinding).where(
                    AgentModelBinding.agent_role_id == row.id
                )
            )).scalar_one_or_none()
            if existing_binding is None:
                db.add(AgentModelBinding(
                    agent_role_id=row.id,
                    provider_id=real_provider.id if real_provider else None,
                    model_name=(real_provider.default_model or (real_provider.model_list or [None])[0]) if real_provider else None,
                ))
            elif existing_binding.provider_id in [stub.id for stub in stub_rows]:
                existing_binding.provider_id = real_provider.id if real_provider else None
                existing_binding.model_name = (real_provider.default_model or (real_provider.model_list or [None])[0]) if real_provider else None
                existing_binding.binding_mode = "auto"
                existing_binding.selection_mode = "auto"

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

        # 8. P7: Genre-specific prompt templates (都市/科幻/历史/悬疑/言情)
        for key, spec in GENRE_PROMPTS.items():
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
                    immutable=True,
                )
                db.add(tpl)
                await db.flush()
            else:
                # Sync metadata
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
            # Ensure v1 exists
            existing = (
                await db.execute(
                    select(PromptVersion).where(PromptVersion.template_id == tpl.id)
                )
            ).scalars().all()
            if not existing:
                ver = PromptVersion(
                    template_id=tpl.id, version=1, body=spec["body"],
                    status="active", change_note="initial seed (genre-specific)",
                )
                db.add(ver)
                await db.flush()
                tpl.active_version_id = ver.id
            else:
                # Auto-bump same as WRITING_PROMPTS
                active = next(
                    (v for v in existing if v.id == tpl.active_version_id),
                    next((v for v in existing if v.status == "active"), existing[0]),
                )
                if active and active.body != spec["body"]:
                    next_no = max(v.version for v in existing) + 1
                    active.status = "deprecated"
                    ver = PromptVersion(
                        template_id=tpl.id, version=next_no, body=spec["body"],
                        status="active",
                        change_note="auto-bump by seed: genre library body changed",
                    )
                    db.add(ver)
                    await db.flush()
                    tpl.active_version_id = ver.id

        # 9. P7: Default genre_prompt_mapping — bind each genre's drafter template
        #    Also bind writing agents as generic fallback (genre="")
        GENRE_DEFAULT_MAPPINGS: list[tuple[str, str, str]] = [
            # (agent_role_key, genre, template_key)
            ("drafter", "玄幻", "drafter_main"),
            ("drafter", "都市", "drafter_urban_smooth"),
            ("drafter", "科幻", "drafter_scifi_hard"),
            ("drafter", "历史", "drafter_historical"),
            ("drafter", "悬疑", "drafter_suspense"),
            ("drafter", "言情", "drafter_romance"),
            # Generic fallbacks (genre="") — these agents use the same template across all genres
            ("critic", "", "critic_main"),
            ("rewriter", "", "rewriter_main"),
            ("planner", "", "planner_main"),
            ("continuity", "", "continuity_main"),
            ("memory_update", "", "memory_update_main"),
        ]
        for agent_key, genre, template_key in GENRE_DEFAULT_MAPPINGS:
            # Find the template
            tpl = (await db.execute(
                select(PromptTemplate).where(PromptTemplate.template_key == template_key)
            )).scalar_one_or_none()
            if tpl is None:
                continue
            # Check if mapping already exists
            existing = (await db.execute(
                select(GenrePromptMapping).where(
                    GenrePromptMapping.agent_role_key == agent_key,
                    GenrePromptMapping.genre == genre,
                    GenrePromptMapping.prompt_template_id == tpl.id,
                )
            )).scalar_one_or_none()
            if existing is None:
                db.add(GenrePromptMapping(
                    agent_role_key=agent_key,
                    genre=genre,
                    prompt_template_id=tpl.id,
                    priority=0,
                    sort_order=0,
                ))

        # 10. P8: Behavior Card knowledge base — default categories + seed cards
        from app.models.behavior_card import (
            BehaviorCard, BehaviorCardTag, BehaviorCardTechnique,
            BehaviorCategory,
        )

        DEFAULT_BEHAVIOR_CATEGORIES: list[dict] = [
            {"name": "主角成长型", "slug": "protagonist_growth", "icon": "🔥", "sort_order": 0},
            {"name": "反派压迫型", "slug": "villain_pressure", "icon": "👁", "sort_order": 1},
            {"name": "女主拉扯型", "slug": "heroine_tension", "icon": "🌙", "sort_order": 2},
            {"name": "配角功能型", "slug": "side_character", "icon": "🧩", "sort_order": 3},
            {"name": "关系冲突型", "slug": "relationship_scene", "icon": "⚡", "sort_order": 4},
            {"name": "待清洗", "slug": "pending_clean", "icon": "🧹", "sort_order": 99},
        ]
        cat_map: dict[str, int] = {}  # slug -> id
        for spec in DEFAULT_BEHAVIOR_CATEGORIES:
            existing_cat = (await db.execute(
                select(BehaviorCategory).where(BehaviorCategory.slug == spec["slug"])
            )).scalar_one_or_none()
            if existing_cat is None:
                cat = BehaviorCategory(**spec)
                db.add(cat)
                await db.flush()
                cat_map[spec["slug"]] = cat.id
            else:
                cat_map[spec["slug"]] = existing_cat.id

        SEED_BEHAVIOR_CARDS: list[dict] = [
            {
                "name": "热血逆袭男主",
                "role_type": "主角",
                "category_slug": "protagonist_growth",
                "avatar_symbol": "🔥",
                "color_theme": "red",
                "summary": "受辱、压抑、爆发、立誓型主角行为模板",
                "behavior_chain": "沉默忍受 → 观察破绽 → 当众反问 → 用结果打脸",
                "emotion_chain": "压抑 → 愤怒 → 冷静 → 爆发 → 立誓",
                "dialogue_style": "短句、硬回应、少解释、结果导向",
                "suitable_scenes": "低谷开局、退婚冲突、师门审判、擂台反杀",
                "unsuitable_scenes": "纯日常、低冲突慢生活、复杂权谋长线",
                "injection_hint": "当章节出现公开打压场景时，优先注入该行为链。",
                "fit_score": 91, "stability_score": 84, "dialogue_score": 78, "generalization_score": 88,
                "tags": [
                    {"tag_type": "role", "tag_name": "主角"},
                    {"tag_type": "role", "tag_name": "热血"},
                    {"tag_type": "scene", "tag_name": "废柴逆袭"},
                    {"tag_type": "scene", "tag_name": "公开受辱"},
                ],
                "techniques": [
                    {"title": "先压尊严，再给反击理由", "content": "先用围观、误解、权威否定制造情绪债。", "example": "长老否定主角资格后，主角抓住规则漏洞反击。", "priority": 0},
                    {"title": "对白短，动作硬", "content": "热血型主角少说话，用行动兑现。对白压缩到6字以内。", "example": "主角不解释，直接把结果甩到对方脸上。", "priority": 1},
                ],
            },
            {
                "name": "理智苟道主角",
                "role_type": "主角",
                "category_slug": "protagonist_growth",
                "avatar_symbol": "🧠",
                "color_theme": "blue",
                "summary": "观察、试探、留后手、小胜型主角行为模板",
                "behavior_chain": "观察风险 → 低成本试探 → 保留退路 → 小幅获利",
                "emotion_chain": "警惕 → 克制 → 推演 → 出手",
                "dialogue_style": "谨慎、留白、少承诺、多反问",
                "suitable_scenes": "资源博弈、信息差利用、密室逃脱、阵营暗战",
                "unsuitable_scenes": "热血擂台、直接对抗、快节奏战斗",
                "injection_hint": "当章节需要主角做判断和取舍时，注入该行为链。",
                "fit_score": 87, "stability_score": 90, "dialogue_score": 72, "generalization_score": 82,
                "tags": [
                    {"tag_type": "role", "tag_name": "主角"},
                    {"tag_type": "role", "tag_name": "理智"},
                    {"tag_type": "scene", "tag_name": "信息差"},
                    {"tag_type": "scene", "tag_name": "资源博弈"},
                ],
                "techniques": [
                    {"title": "先保命，再占便宜", "content": "不要让理智型主角一上来硬刚，先让他判断代价。", "example": "主角先评估三种退路，选代价最小的方案。", "priority": 0},
                ],
            },
            {
                "name": "笑面权谋反派",
                "role_type": "反派",
                "category_slug": "villain_pressure",
                "avatar_symbol": "🎭",
                "color_theme": "purple",
                "summary": "表面示好、暗中设局、借刀杀人的压迫型反派",
                "behavior_chain": "示好 → 套话 → 借刀 → 反咬",
                "emotion_chain": "温和 → 试探 → 冷眼 → 收网",
                "dialogue_style": "礼貌、含蓄、夹枪带棒、暗藏威胁",
                "suitable_scenes": "宫廷权谋、商业暗战、宗门内斗、师徒博弈",
                "unsuitable_scenes": "纯武打擂台、低智热血、单线叙事",
                "injection_hint": "当章节需要反派施加心理压力时，优先使用此卡。",
                "fit_score": 85, "stability_score": 80, "dialogue_score": 90, "generalization_score": 76,
                "tags": [
                    {"tag_type": "role", "tag_name": "反派"},
                    {"tag_type": "role", "tag_name": "腹黑"},
                    {"tag_type": "scene", "tag_name": "高压"},
                    {"tag_type": "scene", "tag_name": "人情陷阱"},
                ],
                "techniques": [
                    {"title": "明夸暗贬，让对手自露破绽", "content": "反派不用直接威胁，用赞美和关心让对方放松警惕。", "example": "反派称赞主角天赋，同时在话语中暗示已掌控主角底牌。", "priority": 0},
                    {"title": "借别人的手，脏自己的刀", "content": "权谋型反派不亲自出手，让第三方代为施压。", "example": "反派通过长老传话，主角的困境全部来自'规则'而非个人。", "priority": 1},
                ],
            },
        ]
        for spec in SEED_BEHAVIOR_CARDS:
            existing_card = (await db.execute(
                select(BehaviorCard).where(BehaviorCard.name == spec["name"])
            )).scalar_one_or_none()
            if existing_card is not None:
                continue
            cat_id = cat_map.get(spec.get("category_slug", ""))
            card = BehaviorCard(
                category_id=cat_id,
                name=spec["name"],
                role_type=spec.get("role_type"),
                avatar_symbol=spec.get("avatar_symbol"),
                color_theme=spec.get("color_theme"),
                summary=spec.get("summary"),
                behavior_chain=spec.get("behavior_chain"),
                emotion_chain=spec.get("emotion_chain"),
                dialogue_style=spec.get("dialogue_style"),
                suitable_scenes=spec.get("suitable_scenes"),
                unsuitable_scenes=spec.get("unsuitable_scenes"),
                injection_hint=spec.get("injection_hint"),
                fit_score=spec.get("fit_score", 0),
                stability_score=spec.get("stability_score", 0),
                dialogue_score=spec.get("dialogue_score", 0),
                generalization_score=spec.get("generalization_score", 0),
                status="ready",
            )
            db.add(card)
            await db.flush()
            # tags
            for t in spec.get("tags", []):
                db.add(BehaviorCardTag(
                    card_id=card.id,
                    tag_type=t["tag_type"],
                    tag_name=t["tag_name"],
                ))
            # techniques
            for idx, tech in enumerate(spec.get("techniques", [])):
                db.add(BehaviorCardTechnique(
                    card_id=card.id,
                    title=tech["title"],
                    content=tech["content"],
                    example=tech.get("example"),
                    priority=tech.get("priority", idx),
                ))
            card.technique_count = len(spec.get("techniques", []))
            card.source_count = 0

        # ------------------------------------------------------------------
        # 11. P10: Agent Memory Layered Pool — 种子记忆
        # ------------------------------------------------------------------
        from app.services.agent_memory_service import (
            _fingerprint, TEMPORARY_TTL_SECONDS, TASK_TTL_SECONDS,
        )

        _projects_mem = (await db.execute(select(Project))).scalars().all()
        if _projects_mem:
            first_project = _projects_mem[0]
            pid = first_project.id
            # 检查是否已有种子记忆
            existing = (await db.execute(
                select(func.count()).where(AgentMemoryEntry.project_id == pid)
            )).scalar() or 0
            if existing == 0:
                SEED_AGENT_MEMORIES = [
                    # 永久记忆
                    {
                        "agent_role": "planner", "agent_name": "Planner Agent",
                        "visibility": "permanent_project", "memory_layer": "permanent",
                        "memory_type": "world_rule",
                        "title": "世界规则：修炼境界体系",
                        "content": "本世界修炼体系分九境：炼气、筑基、金丹、元婴、化神、合体、大乘、渡劫、飞升。每个大境界分初、中、后、巅峰四期。跨境界战斗需要至少两个小境界的差距才有可能。",
                        "tags": ["世界规则", "境界体系", "修炼"],
                        "source_type": "user", "confidence": 1.0, "importance": 1.0,
                        "is_locked": True,
                    },
                    {
                        "agent_role": "planner", "agent_name": "Planner Agent",
                        "visibility": "permanent_project", "memory_layer": "permanent",
                        "memory_type": "character",
                        "title": "主线目标：查清母亲失踪真相",
                        "content": "主角的长期目标是查清母亲失踪的真相。母亲在主角幼年时神秘失踪，留下的唯一线索是一块玉佩。这个目标贯穿全书，是主角行动的核心驱动力。",
                        "tags": ["主线", "母亲", "失踪", "玉佩"],
                        "source_type": "user", "confidence": 1.0, "importance": 1.0,
                        "is_locked": True,
                    },
                    # 长时记忆
                    {
                        "agent_role": "planner", "agent_name": "Planner Agent",
                        "visibility": "shared_project", "memory_layer": "long_term",
                        "memory_type": "character",
                        "title": "主角核心人设：隐忍但有底线",
                        "content": "主角不会为了面子主动冒险，但当亲人遗物被触碰时会爆发。平时隐忍克制，但底线一旦触发会毫不犹豫反击。这种隐忍不是懦弱，而是一种战略性的等待。",
                        "tags": ["主角", "隐忍", "底线触发"],
                        "source_type": "discussion", "confidence": 0.97, "importance": 0.91,
                    },
                    {
                        "agent_role": "continuity", "agent_name": "Continuity Agent",
                        "visibility": "shared_project", "memory_layer": "long_term",
                        "memory_type": "foreshadowing",
                        "title": "母亲玉佩：底线触发器",
                        "content": "母亲留下的玉佩是主角的底线触发器。当玉佩受到威胁时，主角会从隐忍状态切换到爆发状态。这个设定在第9章和第12章已经使用过。",
                        "tags": ["伏笔", "玉佩", "底线", "主角"],
                        "source_type": "discussion", "confidence": 0.95, "importance": 0.88,
                    },
                    {
                        "agent_role": "drafter", "agent_name": "Drafter Agent",
                        "visibility": "shared_project", "memory_layer": "long_term",
                        "memory_type": "style",
                        "title": "文风设定：热血但不油腻",
                        "content": "主角爆发时不使用长段内心独白，而用短句+动作兑现。爆发后的后果必须承接，不能爽完就忘。对白风格偏口语化，避免过度文言。",
                        "tags": ["文风", "热血", "短句", "后果承接"],
                        "source_type": "agent", "confidence": 0.9, "importance": 0.85,
                    },
                    # 任务记忆
                    {
                        "agent_role": "critic", "agent_name": "Critic Agent",
                        "visibility": "shared_project", "memory_layer": "task",
                        "memory_type": "critique",
                        "title": "第12章 Critic 扣分点",
                        "content": "逻辑分 72，主要问题是主角爆发缺少触发器。建议增加长老触碰玉佩的细节作为导火索。节奏分 80，前半段铺垫较好但转折略显突兀。",
                        "tags": ["第12章", "Critic", "扣分"],
                        "source_type": "agent", "confidence": 0.84, "importance": 0.7,
                    },
                    # 临时记忆
                    {
                        "agent_role": "planner", "agent_name": "Planner Agent",
                        "visibility": "shared_project", "memory_layer": "temporary",
                        "memory_type": "chapter_context",
                        "title": "本轮第12章规划上下文",
                        "content": "主角当前处于被宗门怀疑阶段，需要在长老会上自证清白。本轮规划需要考虑：1) 主角如何应对质疑 2) 是否揭露部分实力 3) 长老态度的转折点。",
                        "tags": ["第12章", "规划", "上下文"],
                        "source_type": "agent", "confidence": 0.92, "importance": 0.8,
                    },
                ]
                for spec in SEED_AGENT_MEMORIES:
                    fp = _fingerprint(pid, spec["agent_role"], spec["memory_type"], spec["content"])
                    expires_at = None
                    if spec["memory_layer"] == "temporary":
                        expires_at = datetime.utcnow() + timedelta(seconds=TEMPORARY_TTL_SECONDS)
                    elif spec["memory_layer"] == "task":
                        expires_at = datetime.utcnow() + timedelta(seconds=TASK_TTL_SECONDS)

                    entry = AgentMemoryEntry(
                        project_id=pid,
                        content_fingerprint=fp,
                        expires_at=expires_at,
                        **spec,
                    )
                    db.add(entry)

        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed())
    print("Seed complete.")
