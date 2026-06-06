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

        genre_kws = GENRE_KEYWORDS.get(genre, [genre.lower()])

        for tpl in candidate_templates:
            score = 0.5  # 基准分

            # 历史效果分 (权重 0.5)
            if tpl.id in effect_by_tpl:
                score = 0.5 + effect_by_tpl[tpl.id] * 0.5

            # genre 关键词匹配 (权重 0.2)
            tpl_key = tpl.template_key
            tpl_lower = tpl_key.lower() + (tpl.description or "").lower()
            kw_match = any(kw.lower() in tpl_lower for kw in genre_kws)
            if kw_match:
                score += 0.2

            # 专有 genre 变体加分 (如 "drafter.xuanhuan")
            if genre.lower() in tpl_key.lower():
                score += 0.15

            # 通用 fallback 扣分
            if "default" in tpl_key.lower() or "generic" in tpl_key.lower():
                score -= 0.05

            reason_parts = []
            if tpl.id in effect_by_tpl:
                reason_parts.append(f"历史效果{effect_by_tpl[tpl.id]:.0%}")
            if kw_match:
                reason_parts.append(f"genre关键词匹配")
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

        if dry_run:
            return {
                "agent_role_key": agent_role_key, "genre": genre,
                "selected_template_id": best_tpl.id,
                "selected_template_key": best_tpl.template_key,
                "confidence_score": round(best_score, 4),
                "reason": best_reason,
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
            existing.auto_bind_reason = best_reason
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
                auto_bind_reason=best_reason,
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
            "reason": best_reason,
            "action": action,
        }

    async def auto_fill_all(
        self,
        db: AsyncSession,
        *,
        genres: list[str] | None = None,
        agent_role_keys: list[str] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """批量为所有 (agent, genre) 组合自动填充 prompt.

        Args:
            genres: 要填充的 genre 列表; None 表示所有已注册 genre
            agent_role_keys: 要填充的 agent 列表; None 表示所有已知 agent
            dry_run: 预览模式, 不写 DB
        """
        from app.services.model_capability import AGENT_CAPABILITY_PROFILE
        target_agents = agent_role_keys or list(AGENT_KEY_TO_TEMPLATE_PREFIX.keys())
        target_genres = genres or list(GENRE_KEYWORDS.keys()) + [""]

        batch_id = str(uuid.uuid4())[:8]
        results = []
        for agent_key in target_agents:
            for genre in target_genres:
                try:
                    r = await self.auto_fill_for_agent_genre(
                        db, agent_key, genre,
                        batch_id=batch_id, dry_run=dry_run,
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
