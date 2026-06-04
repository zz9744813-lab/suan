"""P3: /api/project-memory/* — 项目记忆 (Raw + Stable) routes.

P3 spec 04 §10 的 11 个端点. 设计要点:

  1. 7 柜 + 讨论室 — 路由用统一 ``/entities?type=`` 接口 + 3 个
     专用端点 (characters / foreshadows / facts) 覆盖 P3 §5 的所有
     档案柜.

  2. 二次加工 (consolidate) / 讨论 (run) / 应用 (apply) 这 3 个
     "写" 端点 P3 这一轮返回 stub 结果 (processed=N / decided=M
     模拟数). 真正的 MemoryConsolidatorAgent / DiscussionAgent
     实现是 P3.1 范围 (跟 P2 的 DeepStudyCoordinator 走同样节奏).

  3. P3 §5 核心原则 "冲突不单独暴露成冲突档案柜, 直接进入讨论
     室拿裁决结果" — router 不暴露 /conflicts 端点, 冲突只通过
     discussion-decisions 列表查询.

  4. P3 §11 写 "Planner / Draft / Continuity 只读 Stable" — 旧
     memory_characters 表的 read 路径保留 (P3 §6 "保留旧表, 不
     直接删除"), 不在 P3 端点集里直接走. Stable 表是这套端点的
     唯一写目标.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import not_found
from app.models.memory_v2 import (
    DiscussionDecision,
    MemoryTimelineEvent,
    RawMemoryEntry,
    StableCharacterState,
    StableMemoryEntity,
)
from app.models.project import Project
from app.schemas.memory_v2 import (
    ApplyDecisionRequest,
    ApplyDecisionResponse,
    ConsolidateRequest,
    ConsolidateResponse,
    DiscussionDecisionRead,
    MemoryTimelineEventRead,
    ProjectMemoryArchiveOverview,
    ProjectMemoryShelfItem,
    ProjectMemoryShelfResponse,
    RawMemoryEntryRead,
    RunDiscussionRequest,
    StableCharacterStateRead,
    StableMemoryEntityDetail,
    StableMemoryEntityRead,
)

router = APIRouter(prefix="/project-memory", tags=["project-memory"])


# ============================================================
# 1. 书架 — 全部项目的记忆册 + 3 个系统维护册
# ============================================================
@router.get("", response_model=ProjectMemoryShelfResponse)
async def list_project_memory_shelf(
    db: AsyncSession = Depends(get_db),
) -> ProjectMemoryShelfResponse:
    """P3 §4: 第一层书架.

    列出所有"项目记忆册" + 3 本固定的"系统维护册" (原始记忆池 /
    稳定记忆索引 / 讨论裁决记录). 每本项目册带 7 柜 + 原始/裁决计数
    + 健康度评分 (P3 §4 "记忆健康评分").
    """
    projects = (await db.execute(
        select(Project).order_by(Project.pinned.desc(), Project.sort_order.asc(), Project.id.asc())
    )).scalars().all()

    items: list[ProjectMemoryShelfItem] = []
    for p in projects:
        # 7 柜计数 — 一个 GROUP BY entity_type 拿全, 比 7 次 count() 快
        type_counts = dict((await db.execute(
            select(StableMemoryEntity.entity_type, func.count(StableMemoryEntity.id))
            .where(StableMemoryEntity.project_id == p.id)
            .group_by(StableMemoryEntity.entity_type)
        )).all())

        raw_total = (await db.execute(
            select(func.count(RawMemoryEntry.id))
            .where(RawMemoryEntry.project_id == p.id)
        )).scalar_one()
        raw_pending = (await db.execute(
            select(func.count(RawMemoryEntry.id))
            .where(RawMemoryEntry.project_id == p.id, RawMemoryEntry.status == "raw")
        )).scalar_one()

        decision_status_counts = dict((await db.execute(
            select(DiscussionDecision.status, func.count(DiscussionDecision.id))
            .where(DiscussionDecision.project_id == p.id)
            .group_by(DiscussionDecision.status)
        )).all())
        decided = decision_status_counts.get("decided", 0)
        pending = decision_status_counts.get("pending", 0)
        running = decision_status_counts.get("running", 0)
        failed = decision_status_counts.get("failed", 0)
        denom = decided + pending + running + failed
        health = (decided / denom) if denom > 0 else None

        # 最近一次 consolidate 时间 — 我们用最新一条 raw entry 的
        # processed_at 作为近似 (没有专门的 "consolidator_run" 表)
        last_raw = (await db.execute(
            select(RawMemoryEntry.processed_at)
            .where(RawMemoryEntry.project_id == p.id, RawMemoryEntry.processed_at.is_not(None))
            .order_by(RawMemoryEntry.processed_at.desc())
            .limit(1)
        )).scalar_one_or_none()

        items.append(ProjectMemoryShelfItem(
            project_id=p.id,
            project_name=p.name,
            last_consolidated_at=last_raw,
            character_count=type_counts.get("character", 0),
            location_count=type_counts.get("location", 0),
            faction_count=type_counts.get("faction", 0),
            item_count=type_counts.get("item", 0),
            world_rule_count=type_counts.get("world_rule", 0),
            foreshadow_count=type_counts.get("foreshadow", 0),
            hard_fact_count=type_counts.get("hard_fact", 0),
            raw_entry_count=raw_total,
            raw_entry_pending=raw_pending,
            decision_pending=pending,
            decision_running=running,
            health_score=health,
            status=p.status or "active",
        ))

    # 3 本固定的系统维护册 — 不走 DB, 是 frontend 用来进 3 个特殊视图的
    # 入口 (P3 §4 "系统维护册: 原始记忆池 / 稳定记忆索引 / 讨论裁决记录").
    system_books = [
        {"key": "raw_pool",     "label": "原始记忆池",  "subtitle": "MemoryUpdateAgent 写入,Consolidator 处理中"},
        {"key": "stable_index", "label": "稳定记忆索引", "subtitle": "去重 / 合并 / 冲突识别后的最终记忆"},
        {"key": "decisions",    "label": "讨论裁决记录", "subtitle": "Consolidator 不能决定时进讨论室拿结果"},
    ]
    return ProjectMemoryShelfResponse(items=items, system_books=system_books)


# ============================================================
# 2. 档案馆概览 — 一个项目的 7 柜 + 讨论室计数
# ============================================================
@router.get("/{project_id}", response_model=ProjectMemoryArchiveOverview)
async def get_project_memory_archive(
    project_id: int,
    db: AsyncSession = Depends(get_db),
) -> ProjectMemoryArchiveOverview:
    p = await db.get(Project, project_id)
    if p is None:
        raise not_found("Project", project_id)

    type_counts = dict((await db.execute(
        select(StableMemoryEntity.entity_type, func.count(StableMemoryEntity.id))
        .where(StableMemoryEntity.project_id == project_id)
        .group_by(StableMemoryEntity.entity_type)
    )).all())
    counts = {t: type_counts.get(t, 0) for t in (
        "character", "location", "faction", "item", "world_rule",
        "foreshadow", "hard_fact",
    )}

    decision_summary = dict((await db.execute(
        select(DiscussionDecision.status, func.count(DiscussionDecision.id))
        .where(DiscussionDecision.project_id == project_id)
        .group_by(DiscussionDecision.status)
    )).all())
    for s in ("pending", "running", "decided", "failed"):
        decision_summary.setdefault(s, 0)

    last_raw = (await db.execute(
        select(RawMemoryEntry.processed_at)
        .where(RawMemoryEntry.project_id == project_id, RawMemoryEntry.processed_at.is_not(None))
        .order_by(RawMemoryEntry.processed_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    decided = decision_summary.get("decided", 0)
    denom = sum(decision_summary.values())
    health = (decided / denom) if denom > 0 else None

    return ProjectMemoryArchiveOverview(
        project_id=project_id,
        project_name=p.name,
        health_score=health,
        last_consolidated_at=last_raw,
        counts=counts,
        decision_summary=decision_summary,
    )


# ============================================================
# 3. 二次加工 (consolidate) — P3 §6 §8, P3 这一轮 stub
# ============================================================
@router.post("/{project_id}/consolidate", response_model=ConsolidateResponse)
async def consolidate_project_memory(
    project_id: int, body: ConsolidateRequest, db: AsyncSession = Depends(get_db),
) -> ConsolidateResponse:
    """P3 §8 MemoryConsolidatorAgent 入口.

    P3 这一轮返回 stub: 扫一遍 status=raw 计数, 报告 "processed=N
    (全部走 stub 路径)". 真正的 Agent 跑 (合并 / 去重 / 冲突识别) 留
    P3.1 实现. P3 §14 禁 1 "禁止 MemoryUpdateAgent 直接污染稳定
    记忆" 的约束是通过此端点单一入口来保证的 — 任何 raw → stable
    写都必须走 consolidator.
    """
    p = await db.get(Project, project_id)
    if p is None:
        raise not_found("Project", project_id)
    t0 = time.monotonic()
    # 把所有 raw 标成 processed (没有合并/冲突, 全当 accepted), 让
    # 前端能看到 "刚 consolidate 完" 的视觉差异. P3.1 这里会
    # 实际跑 LLM 合并/冲突识别, 然后逐条改 status.
    rows = (await db.execute(
        select(RawMemoryEntry)
        .where(RawMemoryEntry.project_id == project_id, RawMemoryEntry.status == "raw")
        .limit(body.batch_limit)
    )).scalars().all()
    now = datetime.utcnow()
    for r in rows:
        r.status = "processed"
        r.processed_at = now
    await db.flush()
    duration_ms = int((time.monotonic() - t0) * 1000)
    return ConsolidateResponse(
        processed=len(rows),
        merged=0,
        rejected=0,
        needs_discussion=0,
        decided_inline=0,
        decisions_created=[],
        duration_ms=duration_ms,
        cost_usd=0.0,
    )


# ============================================================
# 4. 统一实体列表 (7 柜) — /entities?type=
# ============================================================
@router.get("/{project_id}/entities", response_model=list[StableMemoryEntityRead])
async def list_project_memory_entities(
    project_id: int,
    type: str | None = Query(default=None, description="按 entity_type 过滤 7 柜 (character/location/faction/item/world_rule/foreshadow/hard_fact)"),
    search: str | None = Query(default=None),
    limit: int = Query(default=200, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[StableMemoryEntityRead]:
    """P3 §5 7 柜统一接口. 不传 type = 列全部 active 实体."""
    stmt = select(StableMemoryEntity).where(
        StableMemoryEntity.project_id == project_id,
        StableMemoryEntity.status == "active",
    )
    if type:
        stmt = stmt.where(StableMemoryEntity.entity_type == type)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(StableMemoryEntity.canonical_name.like(like))
    stmt = stmt.order_by(
        StableMemoryEntity.entity_type.asc(),
        StableMemoryEntity.importance.desc(),
        StableMemoryEntity.canonical_name.asc(),
    ).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [StableMemoryEntityRead.model_validate(r) for r in rows]


# ============================================================
# 5. 单实体详情 (含 latest_state + timeline)
# ============================================================
@router.get("/{project_id}/entities/{entity_id}", response_model=StableMemoryEntityDetail)
async def get_project_memory_entity(
    project_id: int, entity_id: int, db: AsyncSession = Depends(get_db),
) -> StableMemoryEntityDetail:
    row = await db.get(StableMemoryEntity, entity_id)
    if row is None or row.project_id != project_id:
        raise not_found("StableMemoryEntity", entity_id)
    detail = StableMemoryEntityDetail.model_validate(row)

    if row.entity_type == "character":
        latest = (await db.execute(
            select(StableCharacterState)
            .where(StableCharacterState.entity_id == entity_id)
            .order_by(StableCharacterState.updated_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        detail.latest_state = (
            StableCharacterStateRead.model_validate(latest) if latest else None
        )
    # 时间线 (按 chapter_index 倒序, 取最近 20 条)
    tl = (await db.execute(
        select(MemoryTimelineEvent)
        .where(MemoryTimelineEvent.entity_id == entity_id)
        .order_by(MemoryTimelineEvent.chapter_index.desc().nulls_last(), MemoryTimelineEvent.created_at.desc())
        .limit(20)
    )).scalars().all()
    detail.timeline = [MemoryTimelineEventRead.model_validate(t) for t in tl]
    return detail


# ============================================================
# 6-7. 专用端点 (P3 §10 显式列出): foreshadows / facts
# ============================================================
@router.get("/{project_id}/foreshadows", response_model=list[StableMemoryEntityRead])
async def list_project_memory_foreshadows(
    project_id: int,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[StableMemoryEntityRead]:
    """P3 §5 伏笔档案柜. status_filter 是 stable 行的 status (active / paid_off / dropped).

    注: P3 §5 把伏笔和硬事实放进了 StableMemoryEntity 表
    (entity_type=foreshadow / hard_fact) 而不是单独表, 这样 7 柜
    走统一 component. status 字段被 overload — entity_type=character
    时是 active / merged / deleted; foreshadow 时是 active /
    paid_off / dropped (跟旧 memory_foreshadows 兼容).
    """
    stmt = select(StableMemoryEntity).where(
        StableMemoryEntity.project_id == project_id,
        StableMemoryEntity.entity_type == "foreshadow",
    )
    if status_filter:
        stmt = stmt.where(StableMemoryEntity.status == status_filter)
    stmt = stmt.order_by(
        StableMemoryEntity.importance.desc(),
        StableMemoryEntity.canonical_name.asc(),
    ).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [StableMemoryEntityRead.model_validate(r) for r in rows]


@router.get("/{project_id}/facts", response_model=list[StableMemoryEntityRead])
async def list_project_memory_facts(
    project_id: int,
    category: str | None = Query(default=None),
    limit: int = Query(default=200, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[StableMemoryEntityRead]:
    """P3 §5 硬事实档案柜. category 是 tags 之一, 走 LIKE 过滤 (P3 阶段
    不给 facts 加 category 列, 用 tags 替代, 简单一点).
    """
    stmt = select(StableMemoryEntity).where(
        StableMemoryEntity.project_id == project_id,
        StableMemoryEntity.entity_type == "hard_fact",
    )
    if category:
        # SQLite JSON 包含查询 — 走 LIKE 兜底, 精确包含关系 (P3.1
        # 切到 JSON_CONTAINS 时再优化).
        like = f'%"{category}"%'
        stmt = stmt.where(StableMemoryEntity.tags.cast(__import__("sqlalchemy").Text).like(like))
    stmt = stmt.order_by(
        StableMemoryEntity.importance.desc(),
        StableMemoryEntity.canonical_name.asc(),
    ).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [StableMemoryEntityRead.model_validate(r) for r in rows]


# ============================================================
# 8. 讨论裁决记录
# ============================================================
@router.get("/{project_id}/discussion-decisions", response_model=list[DiscussionDecisionRead])
async def list_discussion_decisions(
    project_id: int,
    status_filter: str | None = Query(default=None, alias="status"),
    topic_type: str | None = Query(default=None),
    limit: int = Query(default=200, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[DiscussionDecisionRead]:
    """P3 §5 讨论裁决记录 — 唯一暴露冲突的地方 (P3 §5 核心原则: 不
    暴露"冲突档案柜", 全部进 discussion_decisions)."""
    stmt = select(DiscussionDecision).where(
        DiscussionDecision.project_id == project_id,
    )
    if status_filter:
        stmt = stmt.where(DiscussionDecision.status == status_filter)
    if topic_type:
        stmt = stmt.where(DiscussionDecision.topic_type == topic_type)
    stmt = stmt.order_by(DiscussionDecision.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [DiscussionDecisionRead.model_validate(r) for r in rows]


# ============================================================
# 9. 跑讨论 (run) — P3 §9 DiscussionAgent 入口, P3 stub
# ============================================================
@router.post("/{project_id}/discussion-decisions/{decision_id}/run")
async def run_discussion_decision(
    project_id: int, decision_id: int,
    body: RunDiscussionRequest,
    db: AsyncSession = Depends(get_db),
) -> DiscussionDecisionRead:
    """P3 §9 DiscussionAgent 入口.

    P3 这一轮 stub: 把 status 改成 decided, 写一个 "merge_alias" 的
    演示 decision_payload. 真正的 DiscussionAgent (走 R12 讨论室
    或者 fast-path) 留 P3.1. P3 §14 禁 3 "禁止用户手动处理一堆
    冲突列表" — 即便 stub 也模拟自动决定.
    """
    row = await db.get(DiscussionDecision, decision_id)
    if row is None or row.project_id != project_id:
        raise not_found("DiscussionDecision", decision_id)
    row.status = "running"
    await db.flush()
    # P3.1: 这里调 LLM 跑 participants, 等 DiscussionSession 跑完取
    # verdict. P3 stub: 立即给一个默认裁决 (duplicate_entity →
    # merge_alias; 其它 → keep_existing).
    payload: dict[str, Any]
    if row.topic_type == "duplicate_entity":
        # 拿所有 raw entries 的 subject (P3 §12 合并规则: project 内
        # 找最匹配的 stable character, 把所有 subject 收进 aliases).
        # P3 §12 实例: "苏瑶 / 苏瑶儿 / 瑶儿 / 青云宗苏瑶" → canonical=苏瑶,
        # aliases=[苏瑶儿, 瑶儿, 青云宗苏瑶]. 这里的策略:
        #   1) 看项目里有没有一个 stable character 它的 canonical_name
        #      或 aliases 跟某个 subject 重叠 — 选它做 canonical.
        #   2) 没有就选最短的 subject (P3 §12 "苏瑶" 最短) 做 canonical.
        #   3) 其它 subject 全部进 aliases.
        subjects: list[str] = []
        if row.raw_entry_ids:
            for rid in row.raw_entry_ids:
                rr = await db.get(RawMemoryEntry, rid)
                if rr and rr.subject:
                    subjects.append(rr.subject)
        if not subjects:
            subjects = [row.topic_title]
        # 1) 找已有 character 重叠
        canonical = None
        candidates = (await db.execute(
            select(StableMemoryEntity)
            .where(
                StableMemoryEntity.project_id == project_id,
                StableMemoryEntity.entity_type == "character",
                StableMemoryEntity.status == "active",
            )
        )).scalars().all()
        for s in subjects:
            for c in candidates:
                cname = c.canonical_name
                caliases = c.aliases or []
                if s == cname or s in caliases:
                    canonical = cname
                    break
            if canonical:
                break
        # 2) fallback 选最短的 subject
        if not canonical:
            canonical = min(subjects, key=len)
        # 3) 其它 subject (≠ canonical) 进 aliases
        aliases = [s for s in subjects if s != canonical]
        payload = {
            "decision": "merge_alias",
            "canonical_name": canonical,
            "aliases": aliases,
        }
    elif row.topic_type == "foreshadow_unclear":
        payload = {"decision": "keep_active"}
    else:
        payload = {"decision": "keep_existing"}
    row.status = "decided"
    row.decision = payload.get("decision", "keep_existing")
    row.decision_payload = payload
    row.reason = f"[P3 stub] auto-verdict for {row.topic_type} — 真正的 DiscussionAgent 留 P3.1."
    row.decided_by_agent = "DiscussionAgent (P3 stub)"
    row.decided_at = datetime.utcnow()
    await db.flush()
    return DiscussionDecisionRead.model_validate(row)


# ============================================================
# 10. 应用裁决 (apply) — 把 decision_payload 写回 Stable
# ============================================================
@router.post("/{project_id}/discussion-decisions/{decision_id}/apply", response_model=ApplyDecisionResponse)
async def apply_discussion_decision(
    project_id: int, decision_id: int,
    body: ApplyDecisionRequest,
    db: AsyncSession = Depends(get_db),
) -> ApplyDecisionResponse:
    """P3 §9 apply step — 把 DiscussionAgent 的 verdict 落到 Stable
    表. P3 stub: 只对 duplicate_entity 做了真处理, 其它的返回
    applied=True + 空 affected list (等 P3.1 补全).
    """
    row = await db.get(DiscussionDecision, decision_id)
    if row is None or row.project_id != project_id:
        raise not_found("DiscussionDecision", decision_id)
    if row.status != "decided":
        raise HTTPException(400, f"decision #{decision_id} 未裁决, status={row.status}")

    payload = body.decision_payload_override or row.decision_payload or {}
    affected: list[int] = []
    timeline_ids: list[int] = []

    # duplicate_entity → merge_alias: 拿第一篇 raw entry 找到/新建
    # StableMemoryEntity, 把其它 raw entry 的 subject 加到 aliases,
    # 并把它们的 status 改成 merged.
    if row.decision == "merge_alias" and row.raw_entry_ids:
        canonical_name = payload.get("canonical_name") or row.topic_title
        aliases = list(payload.get("aliases") or [])

        # 找 existing entity
        existing = (await db.execute(
            select(StableMemoryEntity)
            .where(
                StableMemoryEntity.project_id == project_id,
                StableMemoryEntity.entity_type == "character",
                StableMemoryEntity.canonical_name == canonical_name,
            )
        )).scalar_one_or_none()
        if existing is None:
            existing = StableMemoryEntity(
                project_id=project_id,
                entity_type="character",
                canonical_name=canonical_name,
                aliases=aliases,
                importance=0.5,
                confidence=0.8,
            )
            db.add(existing)
            await db.flush()
        else:
            # P3 §12 合并别名: existing.aliases + payload.aliases 走 set
            # dedup. 注意 payload.aliases 在 run stub 里可能混了 raw_entry_id
            # (int) 跟字符串, 这层要过滤成纯 str 才不会让 sorted() 抛
            # TypeError (str vs int). P3.1 由 LLM 决策时不会出现这种混入.
            safe_existing = [a for a in (existing.aliases or []) if isinstance(a, str)]
            safe_payload = [a for a in aliases if isinstance(a, str)]
            merged_aliases = safe_existing + safe_payload
            existing.aliases = sorted(set(merged_aliases))
            await db.flush()
        affected.append(existing.id)

        # 把每条 raw entry 标 merged, 指向新 entity
        for raw_id in row.raw_entry_ids:
            raw_row = await db.get(RawMemoryEntry, raw_id)
            if raw_row is None or raw_row.project_id != project_id:
                continue
            if raw_row.canonical_name_safe() != canonical_name:
                # 顺手把 raw.subject 收进 entity.aliases
                if raw_row.subject and raw_row.subject != canonical_name and raw_row.subject not in existing.aliases:
                    cur = [a for a in (existing.aliases or []) if isinstance(a, str)]
                    existing.aliases = sorted(set(cur + [raw_row.subject]))
            raw_row.status = "merged"
            raw_row.merged_into_entity_id = existing.id
            raw_row.processed_at = datetime.utcnow()

        # 写一条 timeline 事件 (P3 §7.4 强制 — 合并本身是状态变更)
        ev = MemoryTimelineEvent(
            project_id=project_id,
            entity_id=existing.id,
            memory_type="character_merge",
            event_title=f"合并到 {canonical_name}",
            event_summary=f"decision #{decision_id} 裁决合并,aliases: {','.join(existing.aliases or [])}",
            before_state=None,
            after_state={"canonical_name": existing.canonical_name, "aliases": existing.aliases},
            created_by="DiscussionAgent apply",
        )
        db.add(ev)
        await db.flush()
        timeline_ids.append(ev.id)

    return ApplyDecisionResponse(
        decision_id=decision_id,
        applied=True,
        affected_entity_ids=affected,
        created_timeline_event_ids=timeline_ids,
        message=("已合并" if affected else f"P3 stub: {row.decision} 不做物理写,等 P3.1"),
    )


# ============================================================
# 11. 原始记忆池 (P3 §7.1) — 调试 / 追溯接口
# ============================================================
@router.get("/{project_id}/raw-entries", response_model=list[RawMemoryEntryRead])
async def list_raw_memory_entries(
    project_id: int,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[RawMemoryEntryRead]:
    """P3 §7.1 原始记忆池, MemoryUpdateAgent 写入. P3 §14 禁 5
    禁止删除, 这里只读不删."""
    stmt = select(RawMemoryEntry).where(RawMemoryEntry.project_id == project_id)
    if status_filter:
        stmt = stmt.where(RawMemoryEntry.status == status_filter)
    stmt = stmt.order_by(RawMemoryEntry.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [RawMemoryEntryRead.model_validate(r) for r in rows]


# 让 RawMemoryEntry 可以安全取 subject 字段 (apply step 用了).
# 这里 monkey-patch 是因为我们没有专门的 schema-side helper, P3
# 直接访问 ORM row 字段最简单. 如果 P3.1 改成 service 层, 这段
# 就可以删了.
def _raw_canonical_name_safe(self) -> str:  # type: ignore[no-redef]
    return self.subject or ""
RawMemoryEntry.canonical_name_safe = _raw_canonical_name_safe  # type: ignore[attr-defined]
