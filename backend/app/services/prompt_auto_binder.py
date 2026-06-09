"""PromptAutoBinder: 自动为 (agent_role_key, genre) 选择最优 prompt 并写入映射表.

NF2 阶段 2 自动化工厂核心服务. 触发时机:
  - Agent 首次运行某 genre 时没有找到映射 (PromptEngine 返回 fallback)
  - 用户点击「一键自动填充」
  - 周期任务批量评估更新

策略:
  1. 找出该 agent_role_key 对应的所有 PromptTemplate (同 key 前缀匹配)
  2. 从 genre_prompt_mappings 读取历史 effect_score
  3. 选 effect_score 最高的模板; 若无历史数据, 使用 genre 关键词匹配
  4. 写入/更新映射, source="auto", locked_by_user=False
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.genre_prompt_map import GenrePromptMapping
from app.models.memory import MemoryCharacter, MemoryForeshadow, MemoryHardFact
from app.models.project import Bible, Outline, Project
from app.models.prompt import PromptTemplate, PromptVersion

logger = logging.getLogger(__name__)

# Agent 角色 key 到 Prompt template key 前缀的映射
# (template key 命名约定: {agent_key}.{variant})
AGENT_KEY_TO_TEMPLATE_PREFIX: dict[str, list[str]] = {
    "planner": ["planner", "plan"],
    "drafter": ["drafter", "draft", "writer"],
    "critic": ["critic", "review"],
    "rewriter": ["rewriter", "rewrite"],
    "continuity": ["continuity", "consistency"],
    "memory_updater": ["memory", "memory_updater"],
    "learner": ["learner", "learn"],
    "study": ["study", "study_agent"],
    "reader_hook": ["reader_hook", "hook"],
    "reader_emotion": ["reader_emotion", "emotion"],
    "reader_logic": ["reader_logic", "logic"],
    "reader_commercial": ["reader_commercial", "commercial"],
    "reader_toxic": ["reader_toxic", "toxic"],
}

# genre 关键词 → 风格 hint (用于模板名匹配打分)
GENRE_KEYWORDS: dict[str, list[str]] = {
    "玄幻": ["xuan", "fantasy", "xuanhuan", "玄幻"],
    "仙侠": ["xianxia", "仙侠", "immortal"],
    "都市": ["urban", "city", "都市", "modern"],
    "历史": ["history", "历史", "ancient"],
    "科幻": ["scifi", "sci", "科幻", "future"],
    "言情": ["romance", "言情", "love"],
    "悬疑": ["mystery", "悬疑", "thriller"],
    "武侠": ["wuxia", "武侠"],
}

ROLE_CATEGORY_HINTS: dict[str, str] = {
    "planner": "writing",
    "drafter": "writing",
    "critic": "review",
    "rewriter": "writing",
    "continuity": "memory",
    "memory_updater": "memory",
    "learner": "study",
    "study": "study",
}

ROLE_TASK_HINTS: dict[str, str] = {
    "planner": "拆解项目题材、设定与记忆，输出章节规划和冲突推进建议。",
    "drafter": "根据项目题材、内容摘要与长期记忆生成正文草稿。",
    "critic": "按题材预期、读者体验与记忆一致性审查章节质量。",
    "rewriter": "依据评审意见和项目记忆改写文本，保持风格与事实连续。",
    "continuity": "检查人物、伏笔、硬事实和世界观是否前后一致。",
    "memory_updater": "从最新内容中抽取人物状态、伏笔、硬事实并更新记忆。",
    "learner": "总结项目内容和拆书资料中的可复用写作技法。",
    "study": "提炼学习材料与项目题材之间的可迁移写法。",
}


def _slug(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in (value or "generic"))
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned[:32] or "generic"


def _trim_text(value: str | None, limit: int = 240) -> str:
    if not value:
        return ""
    text = " ".join(str(value).split())
    return text[:limit]


class PromptAutoBinder:
    """为 (agent_role_key, genre) 自动选择并绑定最优 Prompt 模板."""

    async def auto_fill_for_agent_genre(
        self,
        db: AsyncSession,
        agent_role_key: str,
        genre: str,
        *,
        batch_id: str | None = None,
        dry_run: bool = False,
        project_id: int | None = None,
        allow_generate: bool = True,
    ) -> dict[str, Any]:
        """为指定 (agent, genre) 自动选择并写入最优 prompt.

        Returns:
            {
                "agent_role_key": str,
                "genre": str,
                "selected_template_id": int | None,
                "selected_template_key": str | None,
                "confidence_score": float,
                "reason": str,
                "action": "created" | "updated" | "skipped" | "no_template",
            }
        """
        bid = batch_id or str(uuid.uuid4())[:8]
        project_context = await self._load_project_context(db, project_id, genre)
        effective_genre = genre or project_context.get("genre") or "通用"

        # 1. 检查是否已有 user 锁定的映射 → 跳过
        existing_locked = (await db.execute(
            select(GenrePromptMapping).where(
                and_(
                    GenrePromptMapping.agent_role_key == agent_role_key,
                    GenrePromptMapping.genre == genre,
                    GenrePromptMapping.locked_by_user == True,  # noqa: E712
                )
            )
        )).scalar_one_or_none()

        if existing_locked:
            return {
                "agent_role_key": agent_role_key, "genre": genre,
                "selected_template_id": existing_locked.prompt_template_id,
                "confidence_score": 1.0,
                "reason": "用户锁定，跳过自动填充",
                "action": "skipped",
            }

        # 2. 找候选 templates (按 key 前缀匹配)
        prefixes = AGENT_KEY_TO_TEMPLATE_PREFIX.get(agent_role_key, [agent_role_key])
        all_templates = (await db.execute(select(PromptTemplate))).scalars().all()

        candidate_templates = [
            t for t in all_templates
            if any(t.template_key.startswith(pfx) or pfx in t.template_key.lower() for pfx in prefixes)
        ]

        if not candidate_templates:
            if allow_generate:
                generated_tpl = await self._generate_template(
                    db,
                    agent_role_key=agent_role_key,
                    genre=effective_genre,
                    project_context=project_context,
                    batch_id=bid,
                    dry_run=dry_run,
                )
                reason = self._build_reason(
                    "generated_template",
                    project_context,
                    ["无候选模板，已根据项目上下文生成专用模板"],
                )
                if dry_run:
                    return {
                        "agent_role_key": agent_role_key,
                        "genre": genre,
                        "selected_template_id": None,
                        "selected_template_key": generated_tpl["template_key"],
                        "confidence_score": 0.72,
                        "reason": reason,
                        "reason_json": generated_tpl,
                        "candidate_scores": [],
                        "action": "dry_run",
                    }
                mapping = GenrePromptMapping(
                    agent_role_key=agent_role_key,
                    genre=genre,
                    prompt_template_id=generated_tpl["template_id"],
                    priority=0,
                    source="auto",
                    confidence_score=0.72,
                    auto_bind_reason=reason,
                    locked_by_user=False,
                    auto_fill_batch_id=bid,
                )
                db.add(mapping)
                await db.flush()
                return {
                    "agent_role_key": agent_role_key,
                    "genre": genre,
                    "selected_template_id": generated_tpl["template_id"],
                    "selected_template_key": generated_tpl["template_key"],
                    "confidence_score": 0.72,
                    "reason": reason,
                    "reason_json": generated_tpl,
                    "candidate_scores": [],
                    "action": "created",
                }
            return {
                "agent_role_key": agent_role_key, "genre": genre,
                "selected_template_id": None, "confidence_score": 0.0,
                "reason": f"未找到 {agent_role_key} 对应的 Prompt 模板",
                "action": "no_template",
            }

        # 3. 评分每个候选模板
        scored: list[tuple[float, str, PromptTemplate]] = []

        # 获取历史 effect_score
        existing_maps = (await db.execute(
            select(GenrePromptMapping).where(
                GenrePromptMapping.agent_role_key == agent_role_key
            )
        )).scalars().all()
        effect_by_tpl: dict[int, float] = {
            m.prompt_template_id: m.last_effect_score
            for m in existing_maps
            if m.last_effect_score is not None
        }

        genre_kws = GENRE_KEYWORDS.get(effective_genre, [effective_genre.lower()])

        for tpl in candidate_templates:
            score = 0.5  # 基准分
            reason_parts = []

            # 历史效果分 (权重 0.5)
            if tpl.id in effect_by_tpl:
                score = 0.5 + effect_by_tpl[tpl.id] * 0.5
                reason_parts.append(f"历史效果{effect_by_tpl[tpl.id]:.0%}")

            # genre 关键词匹配 (权重 0.2)
            tpl_key = tpl.template_key
            tpl_lower = tpl_key.lower() + (tpl.description or "").lower()
            kw_match = any(kw.lower() in tpl_lower for kw in genre_kws)
            if kw_match:
                score += 0.2
                reason_parts.append("题材关键词匹配")

            # 专有 genre 变体加分 (如 "drafter.xuanhuan")
            if effective_genre.lower() in tpl_key.lower():
                score += 0.15
                reason_parts.append("模板 key 命中题材")

            context_terms = project_context.get("keywords", [])
            context_hits = [kw for kw in context_terms if kw and kw.lower() in tpl_lower]
            if context_hits:
                score += min(0.12, 0.04 * len(context_hits))
                reason_parts.append(f"项目内容/记忆命中: {', '.join(context_hits[:3])}")

            # 通用 fallback 扣分
            if "default" in tpl_key.lower() or "generic" in tpl_key.lower():
                score -= 0.05
                reason_parts.append("通用模板降权")

            reason = ", ".join(reason_parts) if reason_parts else "基准评分"

            scored.append((min(score, 1.0), reason, tpl))

        if not scored:
            return {
                "agent_role_key": agent_role_key, "genre": genre,
                "selected_template_id": None, "confidence_score": 0.0,
                "reason": "评分后无候选",
                "action": "no_template",
            }

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_reason, best_tpl = scored[0]
        candidate_scores = [
            {
                "template_id": tpl.id,
                "template_key": tpl.template_key,
                "score": round(score, 4),
                "reason": reason,
            }
            for score, reason, tpl in scored[:8]
        ]
        full_reason = self._build_reason(best_reason, project_context, ["从候选模板中自动选择最高分模板"])

        if dry_run:
            return {
                "agent_role_key": agent_role_key,
                "genre": genre,
                "selected_template_id": best_tpl.id,
                "selected_template_key": best_tpl.template_key,
                "confidence_score": round(best_score, 4),
                "reason": full_reason,
                "reason_json": {
                    "summary": full_reason,
                    "project_context": project_context,
                    "selection_basis": best_reason,
                },
                "candidate_scores": candidate_scores,
                "action": "dry_run",
            }

        # 4. 写入/更新映射
        existing = (await db.execute(
            select(GenrePromptMapping).where(
                and_(
                    GenrePromptMapping.agent_role_key == agent_role_key,
                    GenrePromptMapping.genre == genre,
                    GenrePromptMapping.prompt_template_id == best_tpl.id,
                )
            )
        )).scalar_one_or_none()

        if existing:
            existing.confidence_score = best_score
            existing.auto_bind_reason = full_reason
            existing.source = "auto"
            existing.auto_fill_batch_id = bid
            action = "updated"
        else:
            mapping = GenrePromptMapping(
                agent_role_key=agent_role_key,
                genre=genre,
                prompt_template_id=best_tpl.id,
                priority=0,
                source="auto",
                confidence_score=best_score,
                auto_bind_reason=full_reason,
                locked_by_user=False,
                auto_fill_batch_id=bid,
            )
            db.add(mapping)
            action = "created"

        await db.flush()
        logger.info(
            "PromptAutoBinder %s agent=%s genre=%s tpl=%s score=%.2f",
            action, agent_role_key, genre, best_tpl.template_key, best_score,
        )

        return {
            "agent_role_key": agent_role_key,
            "genre": genre,
            "selected_template_id": best_tpl.id,
            "selected_template_key": best_tpl.template_key,
            "confidence_score": round(best_score, 4),
            "reason": full_reason,
            "reason_json": {
                "summary": full_reason,
                "project_context": project_context,
                "selection_basis": best_reason,
            },
            "candidate_scores": candidate_scores,
            "action": action,
        }

    async def _load_project_context(
        self,
        db: AsyncSession,
        project_id: int | None,
        fallback_genre: str,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {
            "project_id": project_id,
            "genre": fallback_genre or "通用",
            "project_name": None,
            "description": "",
            "content_samples": [],
            "memory_samples": [],
            "keywords": [],
        }
        if project_id is None:
            context["keywords"] = [fallback_genre] if fallback_genre else []
            return context

        project = await db.get(Project, project_id)
        if project is None:
            context["keywords"] = [fallback_genre] if fallback_genre else []
            return context

        context["genre"] = fallback_genre or project.genre or "通用"
        context["project_name"] = project.name
        context["description"] = _trim_text(project.description, 360)

        bibles = (await db.execute(
            select(Bible).where(Bible.project_id == project_id, Bible.is_active == True).limit(2)  # noqa: E712
        )).scalars().all()
        outlines = (await db.execute(
            select(Outline).where(Outline.project_id == project_id).order_by(Outline.chapter_no.asc()).limit(5)
        )).scalars().all()
        characters = (await db.execute(
            select(MemoryCharacter).where(MemoryCharacter.project_id == project_id).limit(6)
        )).scalars().all()
        foreshadows = (await db.execute(
            select(MemoryForeshadow).where(MemoryForeshadow.project_id == project_id).limit(5)
        )).scalars().all()
        hard_facts = (await db.execute(
            select(MemoryHardFact).where(MemoryHardFact.project_id == project_id).limit(5)
        )).scalars().all()

        content_samples: list[str] = []
        for bible in bibles:
            content_samples.append(_trim_text(str(bible.content), 220))
        for outline in outlines:
            content_samples.append(_trim_text(f"第{outline.chapter_no}章 {outline.title}: {outline.summary or ''}", 220))

        memory_samples: list[str] = []
        for character in characters:
            tags = ",".join(character.tags or [])
            memory_samples.append(_trim_text(f"人物 {character.name}({character.role}) {tags} {character.base_profile}", 180))
        for foreshadow in foreshadows:
            memory_samples.append(_trim_text(f"伏笔 {foreshadow.name}: {foreshadow.summary}", 180))
        for fact in hard_facts:
            memory_samples.append(_trim_text(f"硬事实 {fact.category}: {fact.fact}", 180))

        keywords = [context["genre"], project.name]
        for text in [context["description"], *content_samples, *memory_samples]:
            for token in str(text).replace("，", " ").replace("。", " ").split():
                cleaned = token.strip("：:,.；;、()（）[]【】")
                if 2 <= len(cleaned) <= 12 and cleaned not in keywords:
                    keywords.append(cleaned)
                if len(keywords) >= 12:
                    break
            if len(keywords) >= 12:
                break

        context["content_samples"] = [s for s in content_samples if s][:8]
        context["memory_samples"] = [s for s in memory_samples if s][:12]
        context["keywords"] = [kw for kw in keywords if kw]
        return context

    def _build_reason(
        self,
        selection_basis: str,
        project_context: dict[str, Any],
        extra: list[str] | None = None,
    ) -> str:
        parts = [selection_basis]
        genre = project_context.get("genre")
        if genre:
            parts.append(f"题材={genre}")
        if project_context.get("description"):
            parts.append("参考项目简介")
        if project_context.get("content_samples"):
            parts.append(f"参考内容样本{len(project_context['content_samples'])}条")
        if project_context.get("memory_samples"):
            parts.append(f"参考记忆{len(project_context['memory_samples'])}条")
        if extra:
            parts.extend(extra)
        return "；".join(parts)

    async def _generate_template(
        self,
        db: AsyncSession,
        *,
        agent_role_key: str,
        genre: str,
        project_context: dict[str, Any],
        batch_id: str,
        dry_run: bool,
    ) -> dict[str, Any]:
        template_key = f"{agent_role_key}.auto.{_slug(genre)}"
        existing = (await db.execute(
            select(PromptTemplate).where(PromptTemplate.template_key == template_key)
        )).scalar_one_or_none()
        change_note = self._build_reason(
            "自动生成模板",
            project_context,
            [f"batch={batch_id}", "生成后自动绑定到提示词矩阵"],
        )
        body = self._render_generated_template(agent_role_key, genre, project_context)
        payload = {
            "template_id": existing.id if existing is not None else None,
            "template_key": template_key,
            "change_note": change_note,
            "project_context": project_context,
            "body_preview": body[:500],
        }
        if dry_run:
            return payload

        if existing is None:
            tpl = PromptTemplate(
                template_key=template_key,
                name=f"自动模板/{agent_role_key}/{genre or '通用'}",
                category=ROLE_CATEGORY_HINTS.get(agent_role_key, "writing"),
                role=agent_role_key,
                scope="project",
                genre=genre,
                description=change_note,
                allowed_inputs=["project", "chapter", "memory", "study"],
                forbidden_inputs=[],
                output_schema=None,
                can_modify=["prompt_versions", "genre_prompt_mappings"],
                cannot_modify=["user_locked_mappings"],
                hard_rules=["必须遵守项目硬事实与用户锁定提示词绑定"],
                immutable=False,
            )
            db.add(tpl)
            await db.flush()
            version_no = 1
        else:
            tpl = existing
            tpl.description = change_note
            version_no = (await db.execute(
                select(PromptVersion.version)
                .where(PromptVersion.template_id == tpl.id)
                .order_by(PromptVersion.version.desc())
                .limit(1)
            )).scalar_one_or_none() or 0
            version_no += 1

        ver = PromptVersion(
            template_id=tpl.id,
            version=version_no,
            body=body,
            status="active",
            change_note=change_note,
        )
        db.add(ver)
        await db.flush()
        tpl.active_version_id = ver.id
        payload["template_id"] = tpl.id
        payload["version_id"] = ver.id
        payload["version"] = version_no
        return payload

    def _render_generated_template(
        self,
        agent_role_key: str,
        genre: str,
        project_context: dict[str, Any],
    ) -> str:
        task = ROLE_TASK_HINTS.get(agent_role_key, "根据项目上下文完成当前 Agent 任务。")
        content = "\n".join(f"- {s}" for s in project_context.get("content_samples", [])[:6]) or "- 暂无内容样本，优先依据项目简介与题材。"
        memory = "\n".join(f"- {s}" for s in project_context.get("memory_samples", [])[:8]) or "- 暂无结构化记忆，输出时显式标注待确认事实。"
        keywords = "、".join(project_context.get("keywords", [])[:10])
        return (
            f"你是 NovelForge 后端自动生成的 {agent_role_key} 提示词模板。\n"
            f"项目题材：{genre or '通用'}\n"
            f"项目名称：{project_context.get('project_name') or '未指定'}\n"
            f"项目简介：{project_context.get('description') or '未提供'}\n"
            f"关键词：{keywords or '无'}\n\n"
            f"任务：{task}\n\n"
            "可参考内容：\n"
            f"{content}\n\n"
            "可参考记忆：\n"
            f"{memory}\n\n"
            "执行规则：\n"
            "1. 优先服从用户显式要求、锁定提示词和项目硬事实。\n"
            "2. 输出必须贴合题材预期，并说明使用了哪些项目内容或记忆依据。\n"
            "3. 对不确定信息使用待确认表述，不得编造已发生事实。\n"
            "4. 如发现内容与记忆冲突，先列出冲突再给出保守建议。\n"
        )


    async def auto_fill_all(
        self,
        db: AsyncSession,
        *,
        genres: list[str] | None = None,
        agent_role_keys: list[str] | None = None,
        dry_run: bool = False,
        project_id: int | None = None,
        batch_id: str | None = None,
        allow_generate: bool = True,
    ) -> dict[str, Any]:
        """批量为所有 (agent, genre) 组合自动填充 prompt.

        Args:
            genres: 要填充的 genre 列表; None 表示所有已注册 genre
            agent_role_keys: 要填充的 agent 列表; None 表示所有已知 agent
            dry_run: 预览模式, 不写 DB
        """
        from app.services.model_capability import AGENT_CAPABILITY_PROFILE
        target_agents = agent_role_keys or list(AGENT_KEY_TO_TEMPLATE_PREFIX.keys())
        if genres is not None:
            target_genres = genres
        elif project_id is not None:
            project_context = await self._load_project_context(db, project_id, "")
            target_genres = [project_context.get("genre") or ""]
        else:
            target_genres = list(GENRE_KEYWORDS.keys()) + [""]

        batch_id = batch_id or str(uuid.uuid4())[:8]
        results = []
        for agent_key in target_agents:
            for genre in target_genres:
                try:
                    r = await self.auto_fill_for_agent_genre(
                        db, agent_key, genre,
                        batch_id=batch_id, dry_run=dry_run,
                        project_id=project_id,
                        allow_generate=allow_generate,
                    )
                    results.append(r)
                except Exception as exc:
                    logger.error(
                        "PromptAutoBinder error agent=%s genre=%s: %s",
                        agent_key, genre, exc,
                    )
                    results.append({
                        "agent_role_key": agent_key, "genre": genre,
                        "action": "error", "reason": str(exc)[:200],
                    })

        created = sum(1 for r in results if r.get("action") == "created")
        updated = sum(1 for r in results if r.get("action") == "updated")
        skipped = sum(1 for r in results if r.get("action") == "skipped")
        no_tpl = sum(1 for r in results if r.get("action") == "no_template")
        errors = sum(1 for r in results if r.get("action") == "error")

        return {
            "batch_id": batch_id,
            "dry_run": dry_run,
            "total": len(results),
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "no_template": no_tpl,
            "errors": errors,
            "details": results,
        }


_binder_singleton: PromptAutoBinder | None = None


def get_prompt_auto_binder() -> PromptAutoBinder:
    global _binder_singleton
    if _binder_singleton is None:
        _binder_singleton = PromptAutoBinder()
    return _binder_singleton
