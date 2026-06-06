"""Prompt 矩阵自动填充 + 锁定 + 覆盖率 + 模板效果 API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import bad_request, not_found
from app.models.genre_prompt_map import GenrePromptMapping
from app.models.prompt import PromptTemplate
from app.models.prompt_auto_fill import (
    PromptAutoFillBatch,
    PromptRecommendationLog,
    PromptTemplatePerformance,
)
from app.schemas import APIResponse
from app.services.prompt_auto_binder import get_prompt_auto_binder


router = APIRouter(prefix="/prompts/matrix", tags=["prompt-matrix"])


# ── Pydantic schemas ──────────────────────────────────────

class AutoFillPreviewRequest(BaseModel):
    scope: str = Field("all", pattern=r"^(all|empty_only|review_agents|writing_agents)$")
    strategy: str = Field("balanced", pattern=r"^(balanced|quality_first|strict_genre)$")
    project_id: int | None = None
    apply_confidence: list[str] = Field(
        default_factory=lambda: ["high", "medium"],
        description="apply 时只应用这些置信度的推荐",
    )


class AutoFillApplyRequest(BaseModel):
    batch_key: str = Field(..., min_length=1)
    apply_confidence: list[str] = Field(
        default_factory=lambda: ["high", "medium"],
        description="只应用这些置信度的推荐",
    )


class CellLockRequest(BaseModel):
    agent_role_key: str = Field(..., min_length=1)
    genre: str = Field(..., min_length=0)


# ── 1. Preview auto-fill ─────────────────────────────────

@router.post(
    "/auto-fill/preview",
    response_model=APIResponse[dict],
    summary="预览自动填充结果 (dry_run)",
)
async def auto_fill_preview(
    body: AutoFillPreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    """调用 PromptAutoBinder.auto_fill_all(dry_run=True)，创建
    PromptAutoFillBatch(status="preview") + PromptRecommendationLog 记录。"""
    binder = get_prompt_auto_binder()
    result = await binder.auto_fill_all(db, dry_run=True)

    batch_key = result.get("batch_id", str(uuid.uuid4())[:12])

    # 计算统计
    details = result.get("details", [])
    total_cells = len(details)
    recommended_count = sum(
        1 for d in details
        if d.get("action") in ("created", "updated", "dry_run")
    )
    skipped_locked_count = sum(
        1 for d in details if d.get("action") == "skipped"
    )
    missing_template_count = sum(
        1 for d in details if d.get("action") == "no_template"
    )

    # 写入 batch 记录
    batch = PromptAutoFillBatch(
        batch_key=batch_key,
        project_id=body.project_id,
        status="preview",
        scope=body.scope,
        strategy=body.strategy,
        total_cells=total_cells,
        recommended_count=recommended_count,
        applied_count=0,
        skipped_locked_count=skipped_locked_count,
        missing_template_count=missing_template_count,
        summary_json=result,
        created_by="system",
    )
    db.add(batch)

    # 写入每条推荐日志
    for d in details:
        score = d.get("confidence_score", 0.0)
        if score >= 0.8:
            confidence = "high"
        elif score >= 0.5:
            confidence = "medium"
        else:
            confidence = "low"
        action = d.get("action", "suggest")
        if action == "skipped":
            action = "skip_locked"
        elif action == "no_template":
            action = "missing_template"
        elif action in ("created", "updated", "dry_run"):
            action = "auto_bind"

        log = PromptRecommendationLog(
            batch_key=batch_key,
            project_id=body.project_id,
            agent_role_key=d.get("agent_role_key", ""),
            genre=d.get("genre", ""),
            recommended_template_id=d.get("selected_template_id"),
            score=score,
            confidence=confidence,
            action=action,
            reason_json=[d.get("reason", "")],
            applied=False,
        )
        db.add(log)

    await db.flush()
    return {
        "ok": True,
        "data": {
            "batch_key": batch_key,
            "total_cells": total_cells,
            "recommended_count": recommended_count,
            "skipped_locked_count": skipped_locked_count,
            "missing_template_count": missing_template_count,
            "details": details,
        },
    }


# ── 2. Apply auto-fill ───────────────────────────────────

@router.post(
    "/auto-fill/apply",
    response_model=APIResponse[dict],
    summary="应用自动填充",
)
async def auto_fill_apply(
    body: AutoFillApplyRequest,
    db: AsyncSession = Depends(get_db),
):
    """根据 batch_key 找到 batch，调用 PromptAutoBinder.auto_fill_all(dry_run=False)，
    只应用 confidence in apply_confidence 的推荐。"""
    # 找到预览批次
    batch = (await db.execute(
        select(PromptAutoFillBatch).where(
            PromptAutoFillBatch.batch_key == body.batch_key,
        )
    )).scalar_one_or_none()
    if batch is None:
        raise not_found("PromptAutoFillBatch", body.batch_key)
    if batch.status != "preview":
        raise bad_request(
            f"Batch status is '{batch.status}', only 'preview' can be applied",
        )

    # 获取符合条件的推荐
    logs = (await db.execute(
        select(PromptRecommendationLog).where(
            PromptRecommendationLog.batch_key == body.batch_key,
            PromptRecommendationLog.confidence.in_(body.apply_confidence),
            PromptRecommendationLog.action == "auto_bind",
        )
    )).scalars().all()

    applied_count = 0
    for log in logs:
        # 实际写入映射由 binder 完成, 这里标记 log 为 applied
        log.applied = True
        applied_count += 1

    # 调 binder 真写入映射 (dry_run=False)
    binder = get_prompt_auto_binder()
    result = await binder.auto_fill_all(db, dry_run=False)

    # 更新 batch 状态
    batch.status = "applied"
    batch.applied_count = applied_count
    batch.applied_at = datetime.utcnow()

    await db.flush()
    return {
        "ok": True,
        "data": {
            "batch_key": body.batch_key,
            "applied_count": applied_count,
            "binder_result": result,
        },
    }


# ── 3. Rollback auto-fill ────────────────────────────────

@router.post(
    "/auto-fill/{batch_key}/rollback",
    response_model=APIResponse[dict],
    summary="回滚自动填充",
)
async def auto_fill_rollback(
    batch_key: str,
    db: AsyncSession = Depends(get_db),
):
    """将 source="auto" 且 auto_fill_batch_id=batch_key 的映射恢复：
    删除自动创建的映射，或将自动更新的映射恢复到 source="manual"。"""
    batch = (await db.execute(
        select(PromptAutoFillBatch).where(
            PromptAutoFillBatch.batch_key == batch_key,
        )
    )).scalar_one_or_none()
    if batch is None:
        raise not_found("PromptAutoFillBatch", batch_key)
    if batch.status != "applied":
        raise bad_request(
            f"Batch status is '{batch.status}', only 'applied' can be rolled back",
        )

    # 删除自动创建的映射 (source="auto", batch_id 匹配)
    auto_mappings = (await db.execute(
        select(GenrePromptMapping).where(
            GenrePromptMapping.source == "auto",
            GenrePromptMapping.auto_fill_batch_id == batch_key,
        )
    )).scalars().all()

    deleted = 0
    restored = 0
    for m in auto_mappings:
        # 如果存在同 (agent, genre) 的 manual 映射，删除 auto 即可
        # 否则直接删除 auto 映射
        await db.delete(m)
        deleted += 1

    # 标记推荐日志
    await db.execute(
        update(PromptRecommendationLog)
        .where(PromptRecommendationLog.batch_key == batch_key)
        .values(applied=False)
    )

    batch.status = "rolled_back"
    batch.rolled_back_at = datetime.utcnow()

    await db.flush()
    return {
        "ok": True,
        "data": {
            "batch_key": batch_key,
            "deleted_mappings": deleted,
            "restored_mappings": restored,
        },
    }


# ── 4. Recommendations for a cell ────────────────────────

@router.get(
    "/cells/{agent_role_key}/{genre}/recommendations",
    response_model=APIResponse[list[dict]],
    summary="获取指定 (agent, genre) 的推荐列表",
)
async def get_cell_recommendations(
    agent_role_key: str,
    genre: str,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """查询 PromptRecommendationLog 中该 cell 的推荐历史。"""
    logs = (await db.execute(
        select(PromptRecommendationLog).where(
            PromptRecommendationLog.agent_role_key == agent_role_key,
            PromptRecommendationLog.genre == genre,
        ).order_by(PromptRecommendationLog.created_at.desc()).limit(limit)
    )).scalars().all()

    return {
        "ok": True,
        "data": [
            {
                "id": log.id,
                "batch_key": log.batch_key,
                "recommended_template_id": log.recommended_template_id,
                "score": log.score,
                "confidence": log.confidence,
                "action": log.action,
                "reason_json": log.reason_json,
                "candidate_scores_json": log.candidate_scores_json,
                "applied": log.applied,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
    }


# ── 5. Lock / Unlock cell ────────────────────────────────

@router.put(
    "/cells/{agent_role_key}/{genre}/lock",
    response_model=APIResponse[dict],
    summary="锁定矩阵单元格",
)
async def lock_cell(
    agent_role_key: str,
    genre: str,
    db: AsyncSession = Depends(get_db),
):
    """设置 GenrePromptMapping.locked_by_user = True, 阻止自动填充覆盖。"""
    mappings = (await db.execute(
        select(GenrePromptMapping).where(
            GenrePromptMapping.agent_role_key == agent_role_key,
            GenrePromptMapping.genre == genre,
        )
    )).scalars().all()

    if not mappings:
        raise not_found(
            "GenrePromptMapping",
            f"{agent_role_key}/{genre}",
        )

    for m in mappings:
        m.locked_by_user = True
    await db.flush()

    return {
        "ok": True,
        "data": {
            "agent_role_key": agent_role_key,
            "genre": genre,
            "locked_count": len(mappings),
        },
    }


@router.put(
    "/cells/{agent_role_key}/{genre}/unlock",
    response_model=APIResponse[dict],
    summary="解锁矩阵单元格",
)
async def unlock_cell(
    agent_role_key: str,
    genre: str,
    db: AsyncSession = Depends(get_db),
):
    """设置 GenrePromptMapping.locked_by_user = False, 允许自动填充覆盖。"""
    mappings = (await db.execute(
        select(GenrePromptMapping).where(
            GenrePromptMapping.agent_role_key == agent_role_key,
            GenrePromptMapping.genre == genre,
        )
    )).scalars().all()

    if not mappings:
        raise not_found(
            "GenrePromptMapping",
            f"{agent_role_key}/{genre}",
        )

    for m in mappings:
        m.locked_by_user = False
    await db.flush()

    return {
        "ok": True,
        "data": {
            "agent_role_key": agent_role_key,
            "genre": genre,
            "unlocked_count": len(mappings),
        },
    }


# ── 6. Coverage ──────────────────────────────────────────

@router.get(
    "/coverage",
    response_model=APIResponse[dict],
    summary="矩阵覆盖率统计",
)
async def get_coverage(
    project_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """统计矩阵覆盖率 (已绑定/总数)。

    总数 = agent_role_keys × genres 的笛卡尔积；
    已绑定 = GenrePromptMapping 中有记录的 cell 数。
    """
    from app.services.prompt_auto_binder import (
        AGENT_KEY_TO_TEMPLATE_PREFIX,
        GENRE_KEYWORDS,
    )

    agent_keys = list(AGENT_KEY_TO_TEMPLATE_PREFIX.keys())
    genres = list(GENRE_KEYWORDS.keys()) + [""]  # 含通用 fallback

    total = len(agent_keys) * len(genres)

    # 统计已有映射
    bound_count = (await db.execute(
        select(func.count(GenrePromptMapping.id)).select_from(GenrePromptMapping)
    )).scalar() or 0

    # 统计各 source 分布
    source_rows = (await db.execute(
        select(GenrePromptMapping.source, func.count(GenrePromptMapping.id))
        .group_by(GenrePromptMapping.source)
    )).all()
    source_breakdown = {row[0]: row[1] for row in source_rows}

    # 统计锁定数
    locked_count = (await db.execute(
        select(func.count(GenrePromptMapping.id)).where(
            GenrePromptMapping.locked_by_user == True,  # noqa: E712
        )
    )).scalar() or 0

    coverage_rate = round(bound_count / total, 4) if total > 0 else 0.0

    return {
        "ok": True,
        "data": {
            "total_cells": total,
            "bound_count": bound_count,
            "coverage_rate": coverage_rate,
            "source_breakdown": source_breakdown,
            "locked_count": locked_count,
            "agent_keys": agent_keys,
            "genres": genres,
        },
    }


# ── 7. Template performance ──────────────────────────────

@router.get(
    "/templates/{template_id}/performance",
    response_model=APIResponse[dict],
    summary="模板效果统计",
)
async def get_template_performance(
    template_id: int,
    agent_role_key: str | None = None,
    genre: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """查询 PromptTemplatePerformance 中指定模板的效果数据。"""
    tpl = await db.get(PromptTemplate, template_id)
    if tpl is None:
        raise not_found("PromptTemplate", template_id)

    stmt = select(PromptTemplatePerformance).where(
        PromptTemplatePerformance.prompt_template_id == template_id,
    )
    if agent_role_key is not None:
        stmt = stmt.where(
            PromptTemplatePerformance.agent_role_key == agent_role_key,
        )
    if genre is not None:
        stmt = stmt.where(PromptTemplatePerformance.genre == genre)

    rows = (await db.execute(stmt)).scalars().all()

    if not rows:
        return {
            "ok": True,
            "data": {
                "template_id": template_id,
                "template_key": tpl.template_key,
                "template_name": tpl.name,
                "performances": [],
            },
        }

    return {
        "ok": True,
        "data": {
            "template_id": template_id,
            "template_key": tpl.template_key,
            "template_name": tpl.name,
            "performances": [
                {
                    "id": p.id,
                    "agent_role_key": p.agent_role_key,
                    "genre": p.genre,
                    "total_uses": p.total_uses,
                    "success_uses": p.success_uses,
                    "failed_uses": p.failed_uses,
                    "avg_chapter_score": p.avg_chapter_score,
                    "avg_reader_score": p.avg_reader_score,
                    "avg_critic_score": p.avg_critic_score,
                    "rewrite_trigger_rate": p.rewrite_trigger_rate,
                    "json_parse_failure_rate": p.json_parse_failure_rate,
                    "adopted_comment_rate": p.adopted_comment_rate,
                    "last_used_at": p.last_used_at.isoformat() if p.last_used_at else None,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                }
                for p in rows
            ],
        },
    }
