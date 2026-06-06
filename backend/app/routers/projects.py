"""Project / Bible / outline routes."""
from __future__ import annotations

import html
import json
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.errors import not_found
from app.models.memory import MemoryCharacter
from app.models.project import Bible, Chapter, ChapterVersion, Outline, Project
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


def _safe_export_stem(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else "_" for ch in name).strip()
    return cleaned[:80] or "novel"


def _attachment_headers(filename: str) -> dict[str, str]:
    return {
        "Content-Disposition": (
            f'attachment; filename="{quote(filename)}"; '
            f"filename*=UTF-8''{quote(filename)}"
        )
    }


def _pick_export_version(versions: list[ChapterVersion]) -> ChapterVersion | None:
    for kind in ("final", "rewrite", "draft"):
        candidates = [v for v in versions if v.version_kind == kind]
        if candidates:
            return max(candidates, key=lambda v: (v.version_no, v.id))
    if versions:
        return max(versions, key=lambda v: (v.created_at, v.id))
    return None


async def _export_payload(db: AsyncSession, project_id: int) -> tuple[Project, list[dict]]:
    project = await db.get(Project, project_id)
    if project is None:
        raise not_found("Project", project_id)
    chapters = (await db.execute(
        select(Chapter)
        .where(Chapter.project_id == project_id)
        .order_by(Chapter.chapter_no.asc(), Chapter.id.asc())
    )).scalars().all()
    chapter_ids = [c.id for c in chapters]
    versions_by_chapter: dict[int, list[ChapterVersion]] = {cid: [] for cid in chapter_ids}
    if chapter_ids:
        versions = (await db.execute(
            select(ChapterVersion)
            .where(ChapterVersion.chapter_id.in_(chapter_ids))
            .order_by(ChapterVersion.chapter_id.asc(), ChapterVersion.version_kind.asc(), ChapterVersion.version_no.asc())
        )).scalars().all()
        for version in versions:
            versions_by_chapter.setdefault(version.chapter_id, []).append(version)
    rows: list[dict] = []
    for chapter in chapters:
        version = _pick_export_version(versions_by_chapter.get(chapter.id, []))
        content = version.content if version else ""
        rows.append({
            "id": chapter.id,
            "chapter_no": chapter.chapter_no,
            "title": chapter.title,
            "status": chapter.status,
            "target_word_count": chapter.target_word_count,
            "actual_word_count": chapter.actual_word_count,
            "score": chapter.current_score,
            "version_kind": version.version_kind if version else None,
            "version_no": version.version_no if version else None,
            "version_score": version.score if version else None,
            "summary": version.summary if version else None,
            "content": content,
        })
    return project, rows


def _render_export(project: Project, chapters: list[dict], export_format: str) -> tuple[str, str, str]:
    exported_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    stem = _safe_export_stem(project.name)
    if export_format in ("markdown", "md"):
        lines = [
            f"# {project.name}",
            "",
            f"- Genre: {project.genre}",
            f"- Status: {project.status}",
            f"- Exported at: {exported_at}",
            f"- Chapters: {len(chapters)}",
            "",
        ]
        for chapter in chapters:
            lines.extend([
                f"## Chapter {chapter['chapter_no']}: {chapter['title']}",
                "",
                chapter["content"].strip() or "[No exported content]",
                "",
            ])
        return "\n".join(lines), "text/markdown; charset=utf-8", f"{stem}.md"
    if export_format == "txt":
        lines = [
            project.name,
            f"Genre: {project.genre}",
            f"Status: {project.status}",
            f"Exported at: {exported_at}",
            "",
        ]
        for chapter in chapters:
            lines.extend([
                f"Chapter {chapter['chapter_no']}: {chapter['title']}",
                "",
                chapter["content"].strip() or "[No exported content]",
                "",
            ])
        return "\n".join(lines), "text/plain; charset=utf-8", f"{stem}.txt"
    if export_format == "json":
        payload = {
            "project": {
                "id": project.id,
                "name": project.name,
                "genre": project.genre,
                "status": project.status,
                "exported_at": exported_at,
            },
            "chapters": chapters,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2), "application/json; charset=utf-8", f"{stem}.json"
    html_chapters = "\n".join(
        "<section>"
        f"<h2>Chapter {c['chapter_no']}: {html.escape(c['title'])}</h2>"
        f"<pre>{html.escape((c['content'] or '[No exported content]').strip())}</pre>"
        "</section>"
        for c in chapters
    )
    doc = (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(project.name)}</title>"
        "<style>body{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;line-height:1.7;max-width:860px;margin:40px auto;padding:0 24px;color:#222}"
        "pre{white-space:pre-wrap;font-family:inherit}section{border-top:1px solid #ddd;padding-top:20px;margin-top:28px}</style>"
        "</head><body>"
        f"<h1>{html.escape(project.name)}</h1>"
        f"<p>Genre: {html.escape(project.genre)} · Status: {html.escape(project.status)} · Exported at: {exported_at}</p>"
        f"{html_chapters}</body></html>"
    )
    return doc, "text/html; charset=utf-8", f"{stem}.html"


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


@router.get("/{project_id}/export")
async def export_project(
    project_id: int,
    export_format: str = Query(default="markdown", alias="format", pattern="^(txt|markdown|md|json|html)$"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    project, chapters = await _export_payload(db, project_id)
    content, media_type, filename = _render_export(project, chapters, export_format)
    return Response(
        content=content,
        media_type=media_type,
        headers=_attachment_headers(filename),
    )


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
