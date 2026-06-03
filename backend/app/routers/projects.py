"""Project / Bible / outline routes."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.errors import not_found
from app.models.memory import MemoryCharacter
from app.models.project import Bible, Chapter, Outline, Project
from app.models.task import AgentTask, WorkerPolicy
from app.schemas import (
    APIResponse,
    BibleRead,
    BibleUpdate,
    ChapterCreate,
    ChapterRead,
    OutlineCreate,
    OutlineRead,
    ProjectCreate,
    ProjectRead,
    ProjectReorderRequest,
    ProjectUpdate,
    WorkerPolicyRead,
    WorkerPolicyUpdate,
)


router = APIRouter(prefix="/projects", tags=["projects"])


async def _project_to_read(db: AsyncSession, p: Project) -> ProjectRead:
    """Hydrate the computed fields (chapter_count / total_words) and
    copy the Round-2 grouping fields onto a ``ProjectRead``. Kept
    in one place so list / get / create / update all stay in sync.
    """
    chap_count = (await db.execute(
        select(Chapter).where(Chapter.project_id == p.id)
    )).scalars().all()
    total_words = sum(c.actual_word_count for c in chap_count)
    return ProjectRead(
        id=p.id, name=p.name, genre=p.genre,
        category=p.category,
        sort_order=p.sort_order,
        pinned=p.pinned,
        last_opened_at=p.last_opened_at,
        target_word_count=p.target_word_count,
        target_chapter_count=p.target_chapter_count,
        description=p.description, status=p.status,
        created_at=p.created_at, updated_at=p.updated_at,
        chapter_count=len(chap_count), total_words=total_words,
    )


@router.get("", response_model=APIResponse[list[ProjectRead]])
async def list_projects(db: AsyncSession = Depends(get_db)) -> APIResponse[list[ProjectRead]]:
    # Round 2: order by pinned DESC, then sort_order ASC, then id ASC.
    # Pinned projects float to the top regardless of bucket; within a
    # bucket, sort_order controls the user's preferred order; id
    # breaks ties for projects that haven't been touched yet.
    rows = (await db.execute(
        select(Project).order_by(
            Project.pinned.desc(),
            Project.sort_order.asc(),
            Project.id.asc(),
        )
    )).scalars().all()
    return {"ok": True, "data": [await _project_to_read(db, p) for p in rows]}


@router.post("", response_model=APIResponse[ProjectRead])
async def create_project(
    body: ProjectCreate, db: AsyncSession = Depends(get_db)
) -> APIResponse[ProjectRead]:
    # Round 2: if the form didn't supply a category, fall back to
    # the genre so the new project lands in the right bucket by
    # default.
    category = body.category or body.genre
    p = Project(
        name=body.name, genre=body.genre,
        category=category,
        pinned=body.pinned,
        target_word_count=body.target_word_count,
        target_chapter_count=body.target_chapter_count,
        description=body.description,
    )
    db.add(p)
    await db.flush()
    # default worker policy
    db.add(WorkerPolicy(project_id=p.id))
    # default bible
    db.add(Bible(project_id=p.id, title="主设定", content={
        "world": "（待 ChiefAgent 生成）",
        "protagonist": "（待设定）",
    }))
    await db.flush()
    return {"ok": True, "data": await _project_to_read(db, p)}


@router.get("/{project_id}", response_model=APIResponse[ProjectRead])
async def get_project(
    project_id: int, db: AsyncSession = Depends(get_db)
) -> APIResponse[ProjectRead]:
    p = await db.get(Project, project_id)
    if p is None:
        raise not_found("Project", project_id)
    # Round 2: every successful read of a project counts as an
    # "open" and stamps ``last_opened_at``. Cheap (one datetime
    # assignment + flush) and gives the chief panel / search a
    # real MRU signal without the frontend having to PATCH.
    p.last_opened_at = datetime.utcnow()
    await db.flush()
    return {"ok": True, "data": await _project_to_read(db, p)}


@router.patch("/{project_id}", response_model=APIResponse[ProjectRead])
async def update_project(
    project_id: int, body: ProjectUpdate, db: AsyncSession = Depends(get_db)
) -> APIResponse[ProjectRead]:
    p = await db.get(Project, project_id)
    if p is None:
        raise not_found("Project", project_id)
    data = body.model_dump(exclude_unset=True)
    # Round 2: ``touch_last_opened`` is a convenience flag — the
    # client just sends ``{ "touch_last_opened": true }`` whenever
    # the user opens the project, and the router stamps the row.
    if data.pop("touch_last_opened", False):
        p.last_opened_at = datetime.utcnow()
    for k, v in data.items():
        setattr(p, k, v)
    await db.flush()
    return {"ok": True, "data": await _project_to_read(db, p)}


@router.post("/reorder", response_model=APIResponse[dict])
async def reorder_projects(
    body: ProjectReorderRequest, db: AsyncSession = Depends(get_db)
) -> APIResponse[dict]:
    """Bulk-update sort_order / category / pinned for the items the
    drag-and-drop frontend just rearranged. Each item only carries
    the fields it needs; missing fields keep their existing values
    (so moving an item within a bucket can omit ``category`` and
    just change ``sort_order``).

    Idempotent: re-running with the same payload is a no-op.
    """
    if not body.items:
        return {"ok": True, "data": {"updated": 0}}
    ids = [item.project_id for item in body.items]
    rows = (await db.execute(
        select(Project).where(Project.id.in_(ids))
    )).scalars().all()
    by_id = {p.id: p for p in rows}
    updated = 0
    for item in body.items:
        p = by_id.get(item.project_id)
        if p is None:
            continue
        p.sort_order = item.sort_order
        if item.category is not None:
            p.category = item.category
        p.pinned = item.pinned
        updated += 1
    await db.flush()
    return {"ok": True, "data": {"updated": updated}}


@router.delete("/{project_id}", response_model=APIResponse[dict])
async def delete_project(
    project_id: int, db: AsyncSession = Depends(get_db)
) -> APIResponse[dict]:
    p = await db.get(Project, project_id)
    if p is None:
        raise not_found("Project", project_id)
    await db.delete(p)
    return {"ok": True, "data": {"deleted": project_id}}


# ----- Bible -----

@router.get("/{project_id}/bible", response_model=APIResponse[BibleRead])
async def get_bible(
    project_id: int, db: AsyncSession = Depends(get_db)
) -> APIResponse[BibleRead]:
    row = (await db.execute(
        select(Bible).where(Bible.project_id == project_id, Bible.is_active.is_(True))
    )).scalar_one_or_none()
    if row is None:
        raise not_found("Bible", project_id)
    return {"ok": True, "data": BibleRead.model_validate(row)}


@router.put("/{project_id}/bible", response_model=APIResponse[BibleRead])
async def update_bible(
    project_id: int, body: BibleUpdate, db: AsyncSession = Depends(get_db)
) -> APIResponse[BibleRead]:
    row = (await db.execute(
        select(Bible).where(Bible.project_id == project_id, Bible.is_active.is_(True))
    )).scalar_one_or_none()
    if row is None:
        raise not_found("Bible", project_id)
    if body.title is not None:
        row.title = body.title
    if body.content is not None:
        row.content = body.content
        row.version += 1
    await db.flush()
    return {"ok": True, "data": BibleRead.model_validate(row)}


# ----- Outline -----

@router.get("/{project_id}/outlines", response_model=APIResponse[list[OutlineRead]])
async def list_outlines(
    project_id: int, db: AsyncSession = Depends(get_db)
) -> APIResponse[list[OutlineRead]]:
    rows = (await db.execute(
        select(Outline).where(Outline.project_id == project_id).order_by(Outline.chapter_no.asc())
    )).scalars().all()
    return {"ok": True, "data": [OutlineRead.model_validate(r) for r in rows]}


@router.post("/{project_id}/outlines", response_model=APIResponse[OutlineRead])
async def create_outline(
    project_id: int, body: OutlineCreate, db: AsyncSession = Depends(get_db)
) -> APIResponse[OutlineRead]:
    row = Outline(project_id=project_id, **body.model_dump())
    db.add(row)
    await db.flush()
    return {"ok": True, "data": OutlineRead.model_validate(row)}


@router.post("/{project_id}/outlines/bulk", response_model=APIResponse[list[OutlineRead]])
async def bulk_create_outlines(
    project_id: int, items: list[OutlineCreate], db: AsyncSession = Depends(get_db)
) -> APIResponse[list[OutlineRead]]:
    rows = [Outline(project_id=project_id, **i.model_dump()) for i in items]
    db.add_all(rows)
    await db.flush()
    return {"ok": True, "data": [OutlineRead.model_validate(r) for r in rows]}


# ----- Chapter (lightweight, real chapter work goes through tasks router) -----

@router.get("/{project_id}/chapters", response_model=APIResponse[list[ChapterRead]])
async def list_chapters(
    project_id: int,
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[ChapterRead]]:
    stmt = select(Chapter).where(Chapter.project_id == project_id)
    if status:
        stmt = stmt.where(Chapter.status == status)
    rows = (await db.execute(stmt.order_by(Chapter.chapter_no.asc()))).scalars().all()
    return {"ok": True, "data": [ChapterRead.model_validate(r) for r in rows]}


@router.post("/{project_id}/chapters", response_model=APIResponse[ChapterRead])
async def create_chapter(
    project_id: int, body: ChapterCreate, db: AsyncSession = Depends(get_db)
) -> APIResponse[ChapterRead]:
    row = Chapter(project_id=project_id, **body.model_dump())
    db.add(row)
    await db.flush()
    return {"ok": True, "data": ChapterRead.model_validate(row)}


# ----- Worker Policy -----

@router.get("/{project_id}/policy", response_model=APIResponse[WorkerPolicyRead])
async def get_policy(
    project_id: int, db: AsyncSession = Depends(get_db)
) -> APIResponse[WorkerPolicyRead]:
    row = (await db.execute(
        select(WorkerPolicy).where(WorkerPolicy.project_id == project_id)
    )).scalar_one_or_none()
    if row is None:
        row = WorkerPolicy(project_id=project_id)
        db.add(row)
        await db.flush()
    return {"ok": True, "data": WorkerPolicyRead.model_validate(row)}


@router.put("/{project_id}/policy", response_model=APIResponse[WorkerPolicyRead])
async def update_policy(
    project_id: int, body: WorkerPolicyUpdate, db: AsyncSession = Depends(get_db)
) -> APIResponse[WorkerPolicyRead]:
    row = (await db.execute(
        select(WorkerPolicy).where(WorkerPolicy.project_id == project_id)
    )).scalar_one_or_none()
    if row is None:
        row = WorkerPolicy(project_id=project_id)
        db.add(row)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.flush()
    return {"ok": True, "data": WorkerPolicyRead.model_validate(row)}
