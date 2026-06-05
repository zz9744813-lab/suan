"""P10: Agent 分层记忆池 — Service 层.

包含 6 个服务:
  - AgentMemoryService         核心 CRUD + 审计日志
  - MemoryWriteService         Agent 写入记忆 (含 fingerprint 去重)
  - MemoryRetrievalService     Agent 检索记忆 (含 access log)
  - MemoryConsolidatorService  记忆整理 (过期/重复/提升/冲突)
  - MemoryAuditorService       冲突检测 + 永久记忆保护
  - MemoryGraphService         记忆图谱
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_memory import (
    AgentMemoryAccessLog,
    AgentMemoryAuditLog,
    AgentMemoryConsolidationJob,
    AgentMemoryEntry,
    AgentMemoryLink,
    MemoryChangeRequest,
)
from app.schemas.agent_memory import (
    AgentMemoryListResponse,
    AgentMemoryStats,
    ChangeRequestCreate,
    ChangeRequestRead,
    ConsolidationJobRead,
    MemoryAccessLogRead,
    MemoryArchiveRequest,
    MemoryAuditLogRead,
    MemoryDemoteRequest,
    MemoryEntryCreate,
    MemoryEntryDetail,
    MemoryEntryListItem,
    MemoryEntryListResponse,
    MemoryEntryRead,
    MemoryEntryUpdate,
    MemoryGraphData,
    MemoryLinkRead,
    MemoryMarkConflictRequest,
    MemoryMergeRequest,
    MemoryProjectStats,
    MemoryPromoteRequest,
)

VALID_LAYERS = ("temporary", "task", "long_term", "permanent")
LAYER_ORDER = {"temporary": 0, "task": 1, "long_term": 2, "permanent": 3}

# 临时记忆默认 TTL
TEMPORARY_TTL_SECONDS = 24 * 3600  # 24 hours
# 任务记忆默认 TTL
TASK_TTL_SECONDS = 30 * 24 * 3600  # 30 days


def _fingerprint(project_id: int, agent_role: str, memory_type: str, content: str) -> str:
    """计算内容指纹, 用于去重."""
    normalized = content.strip().lower()[:2000]
    raw = f"{project_id}:{agent_role}:{memory_type}:{normalized}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _content_preview(content: str, max_len: int = 120) -> str:
    return content[:max_len] + "..." if len(content) > max_len else content


# ============================================================
# AgentMemoryService — 核心 CRUD
# ============================================================

class AgentMemoryService:
    """核心记忆 CRUD + 审计日志."""

    async def create_memory(
        self, db: AsyncSession, project_id: int, payload: MemoryEntryCreate,
    ) -> AgentMemoryEntry:
        """创建记忆条目, 自动计算 fingerprint 和 expires_at."""
        fp = _fingerprint(project_id, payload.agent_role, payload.memory_type, payload.content)

        # 去重: 相同 fingerprint 已存在则更新 usage_count
        existing = (
            await db.execute(
                select(AgentMemoryEntry).where(
                    AgentMemoryEntry.content_fingerprint == fp,
                    AgentMemoryEntry.project_id == project_id,
                    AgentMemoryEntry.deleted_at.is_(None),
                    AgentMemoryEntry.archived_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.usage_count += 1
            existing.last_used_at = datetime.utcnow()
            existing.updated_at = datetime.utcnow()
            await db.flush()
            return existing

        # 计算 expires_at
        expires_at = None
        if payload.memory_layer == "temporary":
            ttl = payload.ttl_seconds or TEMPORARY_TTL_SECONDS
            expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        elif payload.memory_layer == "task":
            ttl = payload.ttl_seconds or TASK_TTL_SECONDS
            expires_at = datetime.utcnow() + timedelta(seconds=ttl)

        entry = AgentMemoryEntry(
            project_id=project_id,
            agent_role=payload.agent_role,
            agent_name=payload.agent_name,
            visibility=payload.visibility,
            memory_layer=payload.memory_layer,
            memory_type=payload.memory_type,
            title=payload.title,
            content=payload.content,
            summary=payload.summary,
            tags_json=payload.tags,
            chapter_id=payload.chapter_id,
            task_id=payload.task_id,
            discussion_thread_id=payload.discussion_thread_id,
            skill_id=payload.skill_id,
            source_type=payload.source_type,
            source_id=payload.source_id,
            source_quote=payload.source_quote,
            source_payload_json=payload.source_payload,
            confidence=payload.confidence,
            importance=payload.importance,
            ttl_seconds=payload.ttl_seconds,
            expires_at=expires_at,
            content_fingerprint=fp,
        )
        db.add(entry)
        await db.flush()

        # 审计日志
        await self._write_audit(
            db, entry.id, project_id, "create", None,
            {"title": entry.title, "layer": entry.memory_layer},
            "agent", payload.agent_role, "创建记忆",
        )
        return entry

    async def update_memory(
        self, db: AsyncSession, memory_id: int, patch: MemoryEntryUpdate, actor: str = "user",
    ) -> AgentMemoryEntry:
        entry = await db.get(AgentMemoryEntry, memory_id)
        if entry is None:
            raise ValueError(f"Memory {memory_id} not found")
        if entry.is_locked and entry.memory_layer == "permanent":
            raise ValueError("永久记忆已锁定, 不能直接修改, 请创建 MemoryChangeRequest")

        before = {"title": entry.title, "content": entry.content[:100], "confidence": entry.confidence}

        for field, val in patch.model_dump(exclude_unset=True).items():
            if field == "tags":
                setattr(entry, "tags_json", val)
            else:
                setattr(entry, field, val)
        entry.updated_at = datetime.utcnow()
        await db.flush()

        await self._write_audit(
            db, memory_id, entry.project_id, "update", before,
            patch.model_dump(exclude_unset=True), actor, actor, "更新记忆",
        )
        return entry

    async def get_memory_detail(self, db: AsyncSession, memory_id: int) -> MemoryEntryDetail | None:
        entry = await db.get(AgentMemoryEntry, memory_id)
        if entry is None or entry.deleted_at is not None:
            return None

        # 加载 links
        links_q = (
            await db.execute(
                select(AgentMemoryLink).where(
                    (AgentMemoryLink.source_memory_id == memory_id)
                    | (AgentMemoryLink.target_memory_id == memory_id),
                )
            )
        ).scalars().all()
        link_reads = [MemoryLinkRead.model_validate(l) for l in links_q]

        # 加载最近审计日志
        audit_q = (
            await db.execute(
                select(AgentMemoryAuditLog)
                .where(AgentMemoryAuditLog.memory_id == memory_id)
                .order_by(desc(AgentMemoryAuditLog.created_at))
                .limit(20)
            )
        ).scalars().all()
        audit_reads = [MemoryAuditLogRead.model_validate(a) for a in audit_q]

        # 加载最近访问日志
        access_q = (
            await db.execute(
                select(AgentMemoryAccessLog)
                .where(AgentMemoryAccessLog.memory_id == memory_id)
                .order_by(desc(AgentMemoryAccessLog.created_at))
                .limit(10)
            )
        ).scalars().all()
        access_reads = [MemoryAccessLogRead.model_validate(a) for a in access_q]

        detail = MemoryEntryDetail.model_validate(entry)
        detail.links = link_reads
        detail.audit_logs = audit_reads
        detail.recent_access_logs = access_reads
        detail.source_payload = entry.source_payload_json
        return detail

    async def list_memories(
        self,
        db: AsyncSession,
        project_id: int,
        *,
        agent_role: str | None = None,
        memory_layer: str | None = None,
        memory_type: str | None = None,
        q: str | None = None,
        tag: str | None = None,
        chapter_id: int | None = None,
        task_id: int | None = None,
        is_conflicted: bool | None = None,
        sort: str = "importance",
        limit: int = 50,
        offset: int = 0,
    ) -> MemoryEntryListResponse:
        stmt = select(AgentMemoryEntry).where(
            AgentMemoryEntry.project_id == project_id,
            AgentMemoryEntry.deleted_at.is_(None),
            AgentMemoryEntry.archived_at.is_(None),
        )

        if agent_role:
            stmt = stmt.where(AgentMemoryEntry.agent_role == agent_role)
        if memory_layer:
            stmt = stmt.where(AgentMemoryEntry.memory_layer == memory_layer)
        if memory_type:
            stmt = stmt.where(AgentMemoryEntry.memory_type == memory_type)
        if q:
            stmt = stmt.where(AgentMemoryEntry.title.ilike(f"%{q}%"))
        if tag:
            stmt = stmt.where(AgentMemoryEntry.tags_json.contains([tag]))
        if chapter_id:
            stmt = stmt.where(AgentMemoryEntry.chapter_id == chapter_id)
        if task_id:
            stmt = stmt.where(AgentMemoryEntry.task_id == task_id)
        if is_conflicted is not None:
            stmt = stmt.where(AgentMemoryEntry.is_conflicted == is_conflicted)

        # count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        # sort
        sort_map = {
            "importance": AgentMemoryEntry.importance.desc(),
            "updated_at": AgentMemoryEntry.updated_at.desc(),
            "confidence": AgentMemoryEntry.confidence.desc(),
            "usage_count": AgentMemoryEntry.usage_count.desc(),
        }
        stmt = stmt.order_by(sort_map.get(sort, AgentMemoryEntry.importance.desc()))
        stmt = stmt.offset(offset).limit(limit)

        rows = (await db.execute(stmt)).scalars().all()
        items = []
        for r in rows:
            item = MemoryEntryListItem.model_validate(r)
            item.content_preview = _content_preview(r.content)
            items.append(item)

        return MemoryEntryListResponse(items=items, total=total)

    async def get_stats(self, db: AsyncSession, project_id: int) -> MemoryProjectStats:
        base = select(AgentMemoryEntry).where(
            AgentMemoryEntry.project_id == project_id,
            AgentMemoryEntry.deleted_at.is_(None),
            AgentMemoryEntry.archived_at.is_(None),
        )

        total = (await db.execute(
            select(func.count()).select_from(base.subquery())
        )).scalar() or 0

        by_layer = {}
        for layer in VALID_LAYERS:
            cnt = (await db.execute(
                select(func.count()).select_from(
                    base.where(AgentMemoryEntry.memory_layer == layer).subquery()
                )
            )).scalar() or 0
            by_layer[layer] = cnt

        by_agent = {}
        agent_roles = (await db.execute(
            select(AgentMemoryEntry.agent_role)
            .where(AgentMemoryEntry.project_id == project_id)
            .distinct()
        )).scalars().all()
        for role in agent_roles:
            cnt = (await db.execute(
                select(func.count()).select_from(
                    base.where(AgentMemoryEntry.agent_role == role).subquery()
                )
            )).scalar() or 0
            by_agent[role] = cnt

        conflict_count = (await db.execute(
            select(func.count()).select_from(
                base.where(AgentMemoryEntry.is_conflicted == True).subquery()  # noqa: E712
            )
        )).scalar() or 0

        dup_count = (await db.execute(
            select(func.count()).select_from(
                base.where(AgentMemoryEntry.is_duplicate_candidate == True).subquery()  # noqa: E712
            )
        )).scalar() or 0

        avg_health = (await db.execute(
            select(func.avg(AgentMemoryEntry.health_score)).select_from(
                base.subquery()
            )
        )).scalar() or 1.0

        return MemoryProjectStats(
            project_id=project_id, total=total,
            by_layer=by_layer, by_agent=by_agent,
            conflict_count=conflict_count,
            duplicate_candidate_count=dup_count,
            health_score=round(float(avg_health), 2),
        )

    async def get_agents(self, db: AsyncSession, project_id: int) -> AgentMemoryListResponse:
        """获取项目的 Agent 列表及其记忆统计."""
        KNOWN_AGENTS = [
            ("planner", "Planner Agent"),
            ("drafter", "Drafter Agent"),
            ("critic", "Critic Agent"),
            ("rewriter", "Rewriter Agent"),
            ("continuity", "Continuity Agent"),
            ("reader", "Reader Agent"),
            ("memory_update", "MemoryUpdate Agent"),
            ("chief", "Chief Agent"),
            ("skill_builder", "SkillBuilder Agent"),
        ]
        items = []
        for role, name in KNOWN_AGENTS:
            base = select(AgentMemoryEntry).where(
                AgentMemoryEntry.project_id == project_id,
                AgentMemoryEntry.agent_role == role,
                AgentMemoryEntry.deleted_at.is_(None),
                AgentMemoryEntry.archived_at.is_(None),
            )
            total = (await db.execute(
                select(func.count()).select_from(base.subquery())
            )).scalar() or 0

            counts = {}
            for layer in VALID_LAYERS:
                cnt = (await db.execute(
                    select(func.count()).select_from(
                        base.where(AgentMemoryEntry.memory_layer == layer).subquery()
                    )
                )).scalar() or 0
                counts[layer] = cnt

            conflict = (await db.execute(
                select(func.count()).select_from(
                    base.where(AgentMemoryEntry.is_conflicted == True).subquery()  # noqa: E712
                )
            )).scalar() or 0

            avg_health = (await db.execute(
                select(func.avg(AgentMemoryEntry.health_score)).select_from(
                    base.subquery()
                )
            )).scalar() or 1.0

            last_written = (await db.execute(
                select(func.max(AgentMemoryEntry.updated_at)).select_from(
                    base.subquery()
                )
            )).scalar()

            items.append(AgentMemoryStats(
                agent_role=role, agent_name=name,
                memory_count=total,
                temporary_count=counts.get("temporary", 0),
                task_count=counts.get("task", 0),
                long_term_count=counts.get("long_term", 0),
                permanent_count=counts.get("permanent", 0),
                conflict_count=conflict,
                health_score=round(float(avg_health), 2),
                last_written_at=last_written,
            ))
        return AgentMemoryListResponse(items=items)

    async def promote_memory(
        self, db: AsyncSession, memory_id: int, payload: MemoryPromoteRequest,
    ) -> AgentMemoryEntry:
        entry = await db.get(AgentMemoryEntry, memory_id)
        if entry is None:
            raise ValueError(f"Memory {memory_id} not found")

        current = LAYER_ORDER.get(entry.memory_layer, 0)
        target = LAYER_ORDER.get(payload.target_layer, 0)
        if target <= current:
            raise ValueError(f"不能从 {entry.memory_layer} 提升到 {payload.target_layer}")

        if payload.target_layer == "permanent":
            entry.is_locked = True

        before_layer = entry.memory_layer
        entry.memory_layer = payload.target_layer
        entry.expires_at = None  # 提升后不再过期
        entry.updated_at = datetime.utcnow()
        await db.flush()

        await self._write_audit(
            db, memory_id, entry.project_id, "promote",
            {"layer": before_layer},
            {"layer": payload.target_layer},
            payload.actor_type, payload.actor_type, payload.reason,
        )
        return entry

    async def demote_memory(
        self, db: AsyncSession, memory_id: int, payload: MemoryDemoteRequest,
    ) -> AgentMemoryEntry:
        entry = await db.get(AgentMemoryEntry, memory_id)
        if entry is None:
            raise ValueError(f"Memory {memory_id} not found")
        if entry.memory_layer == "permanent" and entry.is_locked:
            raise ValueError("锁定的永久记忆不能降级, 请创建 MemoryChangeRequest")

        current = LAYER_ORDER.get(entry.memory_layer, 0)
        target = LAYER_ORDER.get(payload.target_layer, 0)
        if target >= current:
            raise ValueError(f"不能从 {entry.memory_layer} 降级到 {payload.target_layer}")

        before_layer = entry.memory_layer
        entry.memory_layer = payload.target_layer
        if payload.target_layer == "temporary":
            entry.expires_at = datetime.utcnow() + timedelta(seconds=TEMPORARY_TTL_SECONDS)
        elif payload.target_layer == "task":
            entry.expires_at = datetime.utcnow() + timedelta(seconds=TASK_TTL_SECONDS)
        entry.updated_at = datetime.utcnow()
        await db.flush()

        await self._write_audit(
            db, memory_id, entry.project_id, "demote",
            {"layer": before_layer}, {"layer": payload.target_layer},
            payload.actor_type, payload.actor_type, payload.reason,
        )
        return entry

    async def archive_memory(
        self, db: AsyncSession, memory_id: int, payload: MemoryArchiveRequest, actor: str = "user",
    ) -> AgentMemoryEntry:
        entry = await db.get(AgentMemoryEntry, memory_id)
        if entry is None:
            raise ValueError(f"Memory {memory_id} not found")
        if entry.memory_layer == "permanent" and entry.is_locked:
            raise ValueError("锁定的永久记忆不能归档")

        entry.archived_at = datetime.utcnow()
        entry.updated_at = datetime.utcnow()
        await db.flush()

        await self._write_audit(
            db, memory_id, entry.project_id, "archive", None, None,
            actor, actor, payload.reason,
        )
        return entry

    async def merge_memories(
        self, db: AsyncSession, project_id: int, payload: MemoryMergeRequest, actor: str = "user",
    ) -> AgentMemoryEntry:
        """合并多条记忆为一条."""
        entries = []
        for sid in payload.source_ids:
            e = await db.get(AgentMemoryEntry, sid)
            if e and e.project_id == project_id:
                entries.append(e)

        if len(entries) < 2:
            raise ValueError("至少需要 2 条记忆才能合并")

        # 创建合并后的新记忆
        agent_role = entries[0].agent_role
        merged = AgentMemoryEntry(
            project_id=project_id,
            agent_role=agent_role,
            memory_layer=payload.target_layer,
            memory_type=entries[0].memory_type,
            title=payload.merged_title,
            content=payload.merged_content,
            tags_json=entries[0].tags_json,
            source_type="merge",
            confidence=max(e.confidence for e in entries),
            importance=max(e.importance for e in entries),
            content_fingerprint=_fingerprint(
                project_id, agent_role, entries[0].memory_type, payload.merged_content,
            ),
        )
        db.add(merged)
        await db.flush()

        # 归档旧记忆并创建 links
        for e in entries:
            e.archived_at = datetime.utcnow()
            link = AgentMemoryLink(
                project_id=project_id,
                source_memory_id=merged.id,
                target_memory_id=e.id,
                relation_type="supersedes",
                description=f"合并自记忆 {e.id}: {e.title}",
                created_by_agent_role=actor,
            )
            db.add(link)

        await db.flush()

        await self._write_audit(
            db, merged.id, project_id, "merge", None,
            {"source_ids": payload.source_ids, "merged_title": payload.merged_title},
            actor, actor, payload.reason,
        )
        return merged

    async def mark_conflict(
        self, db: AsyncSession, memory_id: int, payload: MemoryMarkConflictRequest, actor: str = "user",
    ) -> AgentMemoryLink:
        entry = await db.get(AgentMemoryEntry, memory_id)
        if entry is None:
            raise ValueError(f"Memory {memory_id} not found")

        target = await db.get(AgentMemoryEntry, payload.conflict_with_memory_id)
        if target is None:
            raise ValueError(f"Target memory {payload.conflict_with_memory_id} not found")

        entry.is_conflicted = True
        target.is_conflicted = True
        entry.updated_at = datetime.utcnow()
        target.updated_at = datetime.utcnow()

        link = AgentMemoryLink(
            project_id=entry.project_id,
            source_memory_id=memory_id,
            target_memory_id=payload.conflict_with_memory_id,
            relation_type="conflicts_with",
            description=payload.reason,
            created_by_agent_role=actor,
        )
        db.add(link)
        await db.flush()

        await self._write_audit(
            db, memory_id, entry.project_id, "conflict_mark", None,
            {"conflict_with": payload.conflict_with_memory_id, "reason": payload.reason},
            actor, actor, payload.reason,
        )
        return link

    async def _write_audit(
        self,
        db: AsyncSession,
        memory_id: int,
        project_id: int,
        action: str,
        before: dict | None,
        after: dict | None,
        actor_type: str,
        actor_role: str | None,
        reason: str | None,
    ):
        log = AgentMemoryAuditLog(
            memory_id=memory_id,
            project_id=project_id,
            action=action,
            before_json=before,
            after_json=after,
            actor_type=actor_type,
            actor_role=actor_role,
            reason=reason,
        )
        db.add(log)
        await db.flush()


# ============================================================
# MemoryWriteService — Agent 写入
# ============================================================

class MemoryWriteService:
    """Agent 写入记忆的便捷方法."""

    def __init__(self):
        self._svc = AgentMemoryService()

    async def write_temporary(
        self, db: AsyncSession, project_id: int, agent_role: str,
        title: str, content: str, **kwargs,
    ) -> AgentMemoryEntry:
        payload = MemoryEntryCreate(
            agent_role=agent_role,
            memory_layer="temporary",
            title=title,
            content=content,
            ttl_seconds=kwargs.pop("ttl_seconds", TEMPORARY_TTL_SECONDS),
            **kwargs,
        )
        return await self._svc.create_memory(db, project_id, payload)

    async def write_task_memory(
        self, db: AsyncSession, project_id: int, agent_role: str,
        task_id: int | None, title: str, content: str, **kwargs,
    ) -> AgentMemoryEntry:
        payload = MemoryEntryCreate(
            agent_role=agent_role,
            memory_layer="task",
            title=title,
            content=content,
            task_id=task_id,
            **kwargs,
        )
        return await self._svc.create_memory(db, project_id, payload)

    async def write_long_term(
        self, db: AsyncSession, project_id: int, agent_role: str,
        title: str, content: str, **kwargs,
    ) -> AgentMemoryEntry:
        payload = MemoryEntryCreate(
            agent_role=agent_role,
            memory_layer="long_term",
            title=title,
            content=content,
            confidence=kwargs.pop("confidence", 0.8),
            **kwargs,
        )
        return await self._svc.create_memory(db, project_id, payload)

    async def request_permanent_write(
        self, db: AsyncSession, project_id: int, agent_role: str,
        title: str, content: str, reason: str, **kwargs,
    ) -> MemoryChangeRequest:
        """Agent 不能直接写永久记忆, 必须申请."""
        # 先写成 long_term
        entry = await self.write_long_term(
            db, project_id, agent_role, title, content, **kwargs,
        )
        # 创建提升申请
        cr = MemoryChangeRequest(
            project_id=project_id,
            memory_id=entry.id,
            request_type="update",
            requested_by_agent_role=agent_role,
            reason=f"申请提升为永久记忆: {reason}",
            proposed_content=content,
        )
        db.add(cr)
        await db.flush()
        return cr


# ============================================================
# MemoryRetrievalService — Agent 检索
# ============================================================

class MemoryRetrievalService:
    """Agent 检索记忆, 并记录 access log."""

    async def retrieve_for_agent(
        self,
        db: AsyncSession,
        project_id: int,
        agent_role: str,
        chapter_id: int | None = None,
        task_id: int | None = None,
        query: str | None = None,
        memory_layers: list[str] | None = None,
        memory_types: list[str] | None = None,
        limit: int = 20,
    ) -> list[AgentMemoryEntry]:
        """检索记忆, 优先级: permanent > long_term > task > temporary."""
        stmt = select(AgentMemoryEntry).where(
            AgentMemoryEntry.project_id == project_id,
            AgentMemoryEntry.deleted_at.is_(None),
            AgentMemoryEntry.archived_at.is_(None),
        ).where(
            (AgentMemoryEntry.visibility == "shared_project")
            | (AgentMemoryEntry.visibility == "permanent_project")
            | (AgentMemoryEntry.visibility == "global_skill")
            | ((AgentMemoryEntry.visibility == "private_agent")
               & (AgentMemoryEntry.agent_role == agent_role))
        )

        if memory_layers:
            stmt = stmt.where(AgentMemoryEntry.memory_layer.in_(memory_layers))
        if memory_types:
            stmt = stmt.where(AgentMemoryEntry.memory_type.in_(memory_types))
        if chapter_id:
            stmt = stmt.where(
                (AgentMemoryEntry.chapter_id == chapter_id)
                | (AgentMemoryEntry.chapter_id.is_(None))
            )
        if task_id:
            stmt = stmt.where(
                (AgentMemoryEntry.task_id == task_id)
                | (AgentMemoryEntry.task_id.is_(None))
            )
        if query:
            stmt = stmt.where(AgentMemoryEntry.title.ilike(f"%{query}%"))

        # 按层级优先 + importance 排序
        stmt = stmt.order_by(
            AgentMemoryEntry.memory_layer.desc(),
            AgentMemoryEntry.importance.desc(),
        ).limit(limit)

        rows = (await db.execute(stmt)).scalars().all()

        # 记录 access log
        for r in rows:
            r.usage_count += 1
            r.last_used_at = datetime.utcnow()
            access_log = AgentMemoryAccessLog(
                memory_id=r.id,
                project_id=project_id,
                agent_role=agent_role,
                task_id=task_id,
                chapter_id=chapter_id,
                access_reason=query or f"{agent_role} 检索记忆",
                injected_into_prompt=True,
            )
            db.add(access_log)

        await db.flush()
        return list(rows)


# ============================================================
# MemoryConsolidatorService — 记忆整理
# ============================================================

class MemoryConsolidatorService:
    """记忆整理: 过期/重复/提升/冲突检测."""

    async def expire_temporary_memories(self, db: AsyncSession) -> int:
        """清理过期临时记忆, 返回清理数量."""
        now = datetime.utcnow()
        stmt = (
            delete(AgentMemoryEntry)
            .where(
                AgentMemoryEntry.memory_layer == "temporary",
                AgentMemoryEntry.expires_at.isnot(None),
                AgentMemoryEntry.expires_at < now,
                AgentMemoryEntry.archived_at.is_(None),
                AgentMemoryEntry.is_locked == False,  # noqa: E712
            )
        )
        result = await db.execute(stmt)
        await db.flush()
        return result.rowcount

    async def dedupe_memories(
        self, db: AsyncSession, project_id: int, agent_role: str | None = None,
    ) -> list[dict]:
        """检测重复记忆, 标记 is_duplicate_candidate."""
        stmt = select(AgentMemoryEntry).where(
            AgentMemoryEntry.project_id == project_id,
            AgentMemoryEntry.deleted_at.is_(None),
            AgentMemoryEntry.archived_at.is_(None),
        )
        if agent_role:
            stmt = stmt.where(AgentMemoryEntry.agent_role == agent_role)

        rows = (await db.execute(stmt)).scalars().all()

        # 按 fingerprint 分组
        fp_groups: dict[str, list[AgentMemoryEntry]] = {}
        for r in rows:
            if r.content_fingerprint:
                fp_groups.setdefault(r.content_fingerprint, []).append(r)

        marked = []
        for fp, group in fp_groups.items():
            if len(group) > 1:
                for entry in group:
                    if not entry.is_duplicate_candidate:
                        entry.is_duplicate_candidate = True
                        entry.updated_at = datetime.utcnow()
                        marked.append({"id": entry.id, "title": entry.title})

        await db.flush()
        return marked

    async def promote_candidates(
        self, db: AsyncSession, project_id: int,
    ) -> list[dict]:
        """自动提升候选: 临时→任务 (被引用>2次), 任务→长时 (confidence>=0.8)."""
        promoted = []
        svc = AgentMemoryService()

        # 临时 → 任务: usage_count >= 2
        temp_rows = (await db.execute(
            select(AgentMemoryEntry).where(
                AgentMemoryEntry.project_id == project_id,
                AgentMemoryEntry.memory_layer == "temporary",
                AgentMemoryEntry.usage_count >= 2,
                AgentMemoryEntry.deleted_at.is_(None),
                AgentMemoryEntry.archived_at.is_(None),
                AgentMemoryEntry.is_locked == False,  # noqa: E712
            )
        )).scalars().all()

        for entry in temp_rows:
            await svc.promote_memory(db, entry.id, MemoryPromoteRequest(
                target_layer="task", reason=f"临时记忆被引用 {entry.usage_count} 次, 自动提升",
                actor_type="system",
            ))
            promoted.append({"id": entry.id, "from": "temporary", "to": "task"})

        # 任务 → 长时: confidence >= 0.8
        task_rows = (await db.execute(
            select(AgentMemoryEntry).where(
                AgentMemoryEntry.project_id == project_id,
                AgentMemoryEntry.memory_layer == "task",
                AgentMemoryEntry.confidence >= 0.8,
                AgentMemoryEntry.deleted_at.is_(None),
                AgentMemoryEntry.archived_at.is_(None),
                AgentMemoryEntry.is_locked == False,  # noqa: E712
            )
        )).scalars().all()

        for entry in task_rows:
            await svc.promote_memory(db, entry.id, MemoryPromoteRequest(
                target_layer="long_term", reason=f"任务记忆置信度 {entry.confidence}>=0.8, 自动提升",
                actor_type="system",
            ))
            promoted.append({"id": entry.id, "from": "task", "to": "long_term"})

        return promoted

    async def check_conflicts(self, db: AsyncSession, project_id: int) -> list[dict]:
        """检测与永久记忆冲突的记忆."""
        permanent = (await db.execute(
            select(AgentMemoryEntry).where(
                AgentMemoryEntry.project_id == project_id,
                AgentMemoryEntry.memory_layer == "permanent",
                AgentMemoryEntry.deleted_at.is_(None),
            )
        )).scalars().all()

        if not permanent:
            return []

        # 简单冲突检测: 同 agent_role + 同 memory_type 标题相似
        conflicts = []
        for perm in permanent:
            similar = (await db.execute(
                select(AgentMemoryEntry).where(
                    AgentMemoryEntry.project_id == project_id,
                    AgentMemoryEntry.memory_layer != "permanent",
                    AgentMemoryEntry.agent_role == perm.agent_role,
                    AgentMemoryEntry.memory_type == perm.memory_type,
                    AgentMemoryEntry.title.ilike(f"%{perm.title[:10]}%"),
                    AgentMemoryEntry.deleted_at.is_(None),
                    AgentMemoryEntry.archived_at.is_(None),
                    AgentMemoryEntry.is_conflicted == False,  # noqa: E712
                )
            )).scalars().all()

            for s in similar:
                s.is_conflicted = True
                s.updated_at = datetime.utcnow()
                link = AgentMemoryLink(
                    project_id=project_id,
                    source_memory_id=s.id,
                    target_memory_id=perm.id,
                    relation_type="conflicts_with",
                    description=f"与永久记忆 '{perm.title}' 潜在冲突",
                    created_by_agent_role="system",
                )
                db.add(link)
                conflicts.append({"id": s.id, "title": s.title, "conflict_with": perm.id})

        await db.flush()
        return conflicts

    async def run_consolidation(
        self, db: AsyncSession, project_id: int, job_types: list[str],
    ) -> dict[str, Any]:
        """运行整理任务."""
        results: dict[str, Any] = {}
        if "expire" in job_types:
            results["expired"] = await self.expire_temporary_memories(db)
        if "dedupe" in job_types:
            results["duplicates_marked"] = await self.dedupe_memories(db, project_id)
        if "promote" in job_types:
            results["promoted"] = await self.promote_candidates(db, project_id)
        if "conflict_check" in job_types:
            results["conflicts"] = await self.check_conflicts(db, project_id)
        return results


# ============================================================
# MemoryAuditorService — 冲突检测 + 永久记忆保护
# ============================================================

class MemoryAuditorService:
    """冲突检测和永久记忆保护."""

    async def create_change_request(
        self, db: AsyncSession, project_id: int, payload: ChangeRequestCreate,
    ) -> MemoryChangeRequest:
        entry = await db.get(AgentMemoryEntry, payload.memory_id)
        if entry is None:
            raise ValueError(f"Memory {payload.memory_id} not found")
        if entry.memory_layer != "permanent":
            raise ValueError("只有永久记忆需要修改申请")

        cr = MemoryChangeRequest(
            project_id=project_id,
            memory_id=payload.memory_id,
            request_type=payload.request_type,
            requested_by_agent_role=None,
            reason=payload.reason,
            proposed_content=payload.proposed_content,
            proposed_patch_json=payload.proposed_patch,
        )
        db.add(cr)
        await db.flush()
        return cr

    async def approve_change_request(
        self, db: AsyncSession, request_id: int, reviewer: str, note: str | None = None,
    ) -> MemoryChangeRequest:
        cr = await db.get(MemoryChangeRequest, request_id)
        if cr is None:
            raise ValueError(f"ChangeRequest {request_id} not found")
        if cr.status != "pending":
            raise ValueError(f"ChangeRequest status is {cr.status}, not pending")

        cr.status = "approved"
        cr.reviewed_by = reviewer
        cr.reviewed_at = datetime.utcnow()
        cr.review_note = note

        # 执行修改
        if cr.request_type == "update" and cr.proposed_content:
            entry = await db.get(AgentMemoryEntry, cr.memory_id)
            if entry:
                entry.content = cr.proposed_content
                entry.updated_at = datetime.utcnow()
        elif cr.request_type == "delete":
            entry = await db.get(AgentMemoryEntry, cr.memory_id)
            if entry:
                entry.deleted_at = datetime.utcnow()
        elif cr.request_type == "demote":
            entry = await db.get(AgentMemoryEntry, cr.memory_id)
            if entry:
                entry.memory_layer = "long_term"
                entry.is_locked = False
                entry.updated_at = datetime.utcnow()
        elif cr.request_type == "unlock":
            entry = await db.get(AgentMemoryEntry, cr.memory_id)
            if entry:
                entry.is_locked = False
                entry.updated_at = datetime.utcnow()

        await db.flush()
        return cr

    async def reject_change_request(
        self, db: AsyncSession, request_id: int, reviewer: str, note: str | None = None,
    ) -> MemoryChangeRequest:
        cr = await db.get(MemoryChangeRequest, request_id)
        if cr is None:
            raise ValueError(f"ChangeRequest {request_id} not found")
        cr.status = "rejected"
        cr.reviewed_by = reviewer
        cr.reviewed_at = datetime.utcnow()
        cr.review_note = note
        await db.flush()
        return cr


# ============================================================
# MemoryGraphService — 记忆图谱
# ============================================================

class MemoryGraphService:
    """记忆关系图谱."""

    async def get_project_graph(
        self, db: AsyncSession, project_id: int, agent_role: str | None = None,
    ) -> MemoryGraphData:
        stmt = select(AgentMemoryEntry).where(
            AgentMemoryEntry.project_id == project_id,
            AgentMemoryEntry.deleted_at.is_(None),
            AgentMemoryEntry.archived_at.is_(None),
        )
        if agent_role:
            stmt = stmt.where(AgentMemoryEntry.agent_role == agent_role)

        entries = (await db.execute(stmt.limit(100))).scalars().all()

        nodes = []
        for e in entries:
            nodes.append({
                "id": f"memory:{e.id}",
                "label": e.title,
                "type": e.memory_type,
                "layer": e.memory_layer,
                "agent": e.agent_role,
                "confidence": e.confidence,
            })

        # 加载 links
        entry_ids = [e.id for e in entries]
        links = []
        if entry_ids:
            link_stmt = select(AgentMemoryLink).where(
                AgentMemoryLink.project_id == project_id,
                AgentMemoryLink.source_memory_id.in_(entry_ids),
            )
            link_rows = (await db.execute(link_stmt)).scalars().all()
            for l in link_rows:
                links.append({
                    "source": f"memory:{l.source_memory_id}",
                    "target": f"memory:{l.target_memory_id}",
                    "type": l.relation_type,
                    "description": l.description,
                })

        return MemoryGraphData(nodes=nodes, edges=links)
