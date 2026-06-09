"""Project / Bible / outline routes."""
from __future__ import annotations

import html
import json
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.errors import bad_request, not_found
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
    ProjectWorkspaceChapter,
    ProjectWorkspaceResponse,
    ProjectWorkspaceTocItem,
    WorkerPolicyRead,
    WorkerPolicyUpdate,
)
from app.schemas.memory import MemoryCharacterRead, MemoryCharacterStateRead
from app.schemas.project import ProjectLaunchRequest
from app.services.project_launch import ProjectLaunchService


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


async def _export_payload(db: AsyncSession, project_id: int) -> tuple[Project, list[dict], dict, list[dict]]:
    project = await db.get(Project, project_id)
    if project is None:
        raise not_found("Project", project_id)
    bible = (await db.execute(
        select(Bible)
        .where(Bible.project_id == project_id)
        .order_by(Bible.version.desc(), Bible.id.desc())
    )).scalars().first()
    outlines = (await db.execute(
        select(Outline)
        .where(Outline.project_id == project_id)
        .order_by(Outline.chapter_no.asc(), Outline.id.asc())
    )).scalars().all()
    characters = (await db.execute(
        select(MemoryCharacter)
        .where(MemoryCharacter.project_id == project_id)
        .order_by(MemoryCharacter.id.asc())
    )).scalars().all()
    meta = {
        "bible": {
            "id": bible.id,
            "version": bible.version,
            "content": bible.content,
            "created_at": bible.created_at.isoformat() if bible.created_at else None,
        } if bible else None,
        "outlines": [
            {
                "id": item.id,
                "chapter_no": item.chapter_no,
                "title": item.title,
                "summary": item.summary,
                "target_word_count": item.target_word_count,
            }
            for item in outlines
        ],
    }
    character_rows = [
        {
            "id": c.id,
            "name": c.name,
            "aliases": c.aliases,
            "role": c.role,
            "base_profile": c.base_profile,
        }
        for c in characters
    ]
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
    return project, rows, meta, character_rows


def _render_export(project: Project, chapters: list[dict], export_format: str, meta: dict | None = None, characters: list[dict] | None = None) -> tuple[str, str, str]:
    meta = meta or {}
    characters = characters or []
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
                "description": project.description,
                "genre": project.genre,
                "category": project.category,
                "status": project.status,
                "target_word_count": project.target_word_count,
                "target_chapter_count": project.target_chapter_count,
                "exported_at": exported_at,
            },
            "bible": meta.get("bible"),
            "outlines": meta.get("outlines", []),
            "characters": characters,
            "chapters": chapters,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2), "application/json; charset=utf-8", f"{stem}.json"
    bible_html = ""
    if meta.get("bible"):
        bible_html = (
            "<section><h2>作品设定</h2>"
            f"<pre>{html.escape(json.dumps(meta['bible'].get('content') or {}, ensure_ascii=False, indent=2))}</pre>"
            "</section>"
        )
    outline_html = "".join(
        "<li>"
        f"<strong>第 {o['chapter_no']} 章：{html.escape(o['title'])}</strong>"
        f"<p>{html.escape(o.get('summary') or '')}</p>"
        "</li>"
        for o in meta.get("outlines", [])
    )
    characters_html = "".join(
        "<li>"
        f"<strong>{html.escape(c.get('name') or '')}</strong>"
        f"<p>{html.escape(json.dumps(c.get('base_profile') or {}, ensure_ascii=False))}</p>"
        "</li>"
        for c in characters
    )
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
        "<style>body{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;line-height:1.7;max-width:920px;margin:40px auto;padding:0 24px;color:#222}"
        "pre{white-space:pre-wrap;font-family:inherit;background:#f7f7f7;padding:14px;border-radius:8px}section{border-top:1px solid #ddd;padding-top:20px;margin-top:28px}"
        "li{margin:10px 0}nav{background:#fafafa;border:1px solid #eee;border-radius:12px;padding:14px;margin:18px 0}</style>"
        "</head><body>"
        f"<h1>{html.escape(project.name)}</h1>"
        f"<p>Genre: {html.escape(project.genre)} · Status: {html.escape(project.status)} · Exported at: {exported_at}</p>"
        f"{bible_html}"
        f"<section><h2>大纲</h2><ol>{outline_html}</ol></section>"
        f"<section><h2>人物卡</h2><ul>{characters_html}</ul></section>"
        f"<section><h2>正文</h2></section>{html_chapters}</body></html>"
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
async def list_projects(
    include_system: bool = Query(False, description="包含拆书/系统/DeepStudy 内部项目, 默认 False"),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[ProjectRead]]:
    # Round 2: order by pinned DESC, then sort_order ASC, then id ASC.
    # Pinned projects float to the top regardless of bucket; within a
    # bucket, sort_order controls the user's preferred order; id
    # breaks ties for projects that haven't been touched yet.
    #
    # P0 修复: 默认隐藏拆书·公共 / category in (study, deepstudy, __system_deepstudy) /
    # genre in (system, study, deepstudy) / name="__NF2_SYSTEM_DEEPSTUDY__"
    # 这些是 DeepStudy 自动建的系统占位项目, 不应在小说项目书架出现。
    # 审计 / 调试页加 include_system=true 拿到全部。
    stmt = select(Project)
    if not include_system:
        from sqlalchemy import or_  # SQLite NULL NOT IN 踩坑防护
        stmt = stmt.where(
            Project.name.notin_(["拆书·公共", "__NF2_SYSTEM_DEEPSTUDY__"]),
            or_(
                Project.category.is_(None),
                ~Project.category.in_(["study", "deepstudy", "__system_deepstudy"]),
            ),
            or_(
                Project.genre.is_(None),
                ~Project.genre.in_(["system", "study", "deepstudy"]),
            ),
        )
    rows = (await db.execute(
        stmt.order_by(
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
    #
    # P0 修复: 字段 trim + name 必填保护 (前端虽然校验了, 后端兜底)。
    name = (body.name or "").strip()
    if not name:
        raise bad_request("项目名称不能为空。")
    if len(name) > 200:
        raise bad_request("项目名称不能超过 200 字。")
    genre = (body.genre or "玄幻").strip() or "玄幻"
    category_src = (body.category or body.genre or "").strip() or genre
    description = (body.description or "").strip() or None
    p = Project(
        name=name, genre=genre,
        category=category_src,
        pinned=body.pinned,
        target_word_count=body.target_word_count,
        target_chapter_count=body.target_chapter_count,
        description=description,
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


@router.get("/{project_id}/workspace", response_model=APIResponse[ProjectWorkspaceResponse])
async def get_project_workspace(
    project_id: int,
    chapter_id: int | None = Query(default=None),
    chapter_no: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ProjectWorkspaceResponse]:
    """Return the book-internal second layer for one project.

    A project is the book. This endpoint gathers the pieces the UI needs
    when the user opens that book from the shelf: table of contents,
    selected chapter text, world/bible, characters, and recent user tasks.
    """
    project = await db.get(Project, project_id)
    if project is None:
        raise not_found("Project", project_id)
    project.last_opened_at = datetime.utcnow()

    bible = (await db.execute(
        select(Bible).where(Bible.project_id == project_id, Bible.is_active.is_(True))
    )).scalar_one_or_none()

    outlines = (await db.execute(
        select(Outline)
        .where(Outline.project_id == project_id)
        .order_by(Outline.chapter_no.asc(), Outline.id.asc())
    )).scalars().all()

    chapters = (await db.execute(
        select(Chapter)
        .where(Chapter.project_id == project_id)
        .order_by(Chapter.chapter_no.asc(), Chapter.id.asc())
    )).scalars().all()
    chapter_ids = [chapter.id for chapter in chapters]

    versions_by_chapter: dict[int, list[ChapterVersion]] = {cid: [] for cid in chapter_ids}
    if chapter_ids:
        versions = (await db.execute(
            select(ChapterVersion)
            .where(ChapterVersion.chapter_id.in_(chapter_ids))
            .order_by(
                ChapterVersion.chapter_id.asc(),
                ChapterVersion.version_kind.asc(),
                ChapterVersion.version_no.asc(),
                ChapterVersion.id.asc(),
            )
        )).scalars().all()
        for version in versions:
            versions_by_chapter.setdefault(version.chapter_id, []).append(version)

    outline_by_no = {outline.chapter_no: outline for outline in outlines}
    chapter_by_no = {chapter.chapter_no: chapter for chapter in chapters}
    selected: Chapter | None = None
    if chapter_id is not None:
        selected = next((chapter for chapter in chapters if chapter.id == chapter_id), None)
    if selected is None and chapter_no is not None:
        selected = chapter_by_no.get(chapter_no)
    if selected is None and chapters:
        selected = chapters[0]

    selected_version = _pick_export_version(versions_by_chapter.get(selected.id, [])) if selected else None
    selected_no = selected.chapter_no if selected else chapter_no

    toc: list[ProjectWorkspaceTocItem] = []
    for no in sorted(set(outline_by_no) | set(chapter_by_no)):
        outline = outline_by_no.get(no)
        chapter = chapter_by_no.get(no)
        picked = _pick_export_version(versions_by_chapter.get(chapter.id, [])) if chapter else None
        toc.append(ProjectWorkspaceTocItem(
            chapter_no=no,
            title=(chapter.title if chapter else outline.title if outline else f"Chapter {no}"),
            outline_id=outline.id if outline else None,
            chapter_id=chapter.id if chapter else None,
            outline_summary=outline.summary if outline else None,
            target_word_count=(
                chapter.target_word_count if chapter
                else outline.target_word_count if outline else 0
            ),
            actual_word_count=chapter.actual_word_count if chapter else 0,
            status=chapter.status if chapter else outline.status if outline else "outline",
            has_content=bool(picked and (picked.content or "").strip()),
            selected=(selected_no == no),
        ))

    selected_payload: ProjectWorkspaceChapter | None = None
    if selected is not None:
        outline = outline_by_no.get(selected.chapter_no)
        selected_payload = ProjectWorkspaceChapter(
            id=selected.id,
            chapter_no=selected.chapter_no,
            title=selected.title,
            status=selected.status,
            target_word_count=selected.target_word_count,
            actual_word_count=selected.actual_word_count,
            current_score=selected.current_score,
            outline_id=selected.outline_id,
            outline_summary=outline.summary if outline else None,
            version_id=selected_version.id if selected_version else None,
            version_kind=selected_version.version_kind if selected_version else None,
            version_no=selected_version.version_no if selected_version else None,
            version_score=selected_version.score if selected_version else None,
            summary=selected_version.summary if selected_version else None,
            content=selected_version.content if selected_version else "",
            updated_at=selected.updated_at,
        )

    character_rows = (await db.execute(
        select(MemoryCharacter)
        .options(selectinload(MemoryCharacter.states))
        .where(MemoryCharacter.project_id == project_id)
        .order_by(MemoryCharacter.id.asc())
    )).scalars().all()
    characters = [
        MemoryCharacterRead(
            id=character.id,
            project_id=character.project_id,
            name=character.name,
            aliases=character.aliases,
            role=character.role,
            tags=character.tags,
            base_profile=character.base_profile,
            latest_state=(
                MemoryCharacterStateRead.model_validate(character.states[0])
                if character.states else None
            ),
        )
        for character in character_rows
    ]

    latest_tasks = (await db.execute(
        select(AgentTask)
        .where(
            AgentTask.project_id == project_id,
            or_(AgentTask.visibility.is_(None), AgentTask.visibility != "internal"),
        )
        .order_by(AgentTask.created_at.desc(), AgentTask.id.desc())
        .limit(10)
    )).scalars().all()
    task_items = [
        {
            "id": task.id,
            "project_id": task.project_id,
            "chapter_id": task.chapter_id,
            "task_type": task.task_type,
            "task_kind": task.task_kind,
            "display_title": task.display_title,
            "status": task.status,
            "error": task.error,
            "progress_current": task.progress_current,
            "progress_total": task.progress_total,
            "cost_usd": task.cost_usd,
            "input_tokens": task.input_tokens,
            "output_tokens": task.output_tokens,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "finished_at": task.finished_at,
        }
        for task in latest_tasks
    ]

    payload = ProjectWorkspaceResponse(
        project=await _project_to_read(db, project),
        bible=BibleRead.model_validate(bible) if bible else None,
        characters=characters,
        toc=toc,
        selected_chapter=selected_payload,
        latest_tasks=task_items,
    )
    await db.flush()
    return {"ok": True, "data": payload}


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
    project, chapters, meta, characters = await _export_payload(db, project_id)
    content, media_type, filename = _render_export(project, chapters, export_format, meta, characters)
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
    rows = (await db.execute(
        stmt.order_by(
            Chapter.chapter_no.asc(),
            Chapter.actual_word_count.desc(),
            Chapter.updated_at.desc(),
            Chapter.id.desc(),
        )
    )).scalars().all()
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


# ----- Project Launch (双模式创作启动) -----

@router.post("/{project_id}/launch", response_model=APIResponse)
async def launch_project(
    project_id: int, body: ProjectLaunchRequest, db: AsyncSession = Depends(get_db)
) -> APIResponse:
    """启动创作 — 模式一(半自动) / 模式二(全自动)。"""
    svc = ProjectLaunchService(db)
    if body.mode == "semi_auto":
        result = await svc.launch_semi_auto(
            project_id,
            outline_text=body.outline_text,
            character_text=body.character_text,
            bible_text=body.bible_text,
        )
    elif body.mode == "full_auto":
        result = await svc.launch_full_auto(project_id)
    else:
        raise bad_request(f"不支持的启动模式: {body.mode}")

    # 阶段 3.6: 默认走 Redis 队列. 老 httpx 兜底仅在 worker_run_in_process=True
    # 时启用, 用于本地 SQLite 回归.
    from app.core.config import settings

    if not settings.worker_run_in_process:
        first_task_type = (result or {}).get("first_task_type") or "chapter_pipeline"
        try:
            from app.workers.writing_pipeline import (
                enqueue_bootstrap_task,
                enqueue_chapter_task,
            )
            if str(first_task_type) == "project_bootstrap":
                task_id = (result or {}).get("bootstrap_task_id") or (result or {}).get("first_task_id")
                if isinstance(task_id, int):
                    result["queued_job_id"] = await enqueue_bootstrap_task(task_id)
            else:
                chapter_id = (result or {}).get("first_chapter_id")
                if isinstance(chapter_id, int):
                    result["queued_job_id"] = await enqueue_chapter_task(chapter_id)
        except Exception as exc:
            # 入队失败不影响 HTTP 响应, 但返回给前端用于诊断
            result["queue_error"] = str(exc)
    else:
        # 老路径: HTTP 自调 /api/worker/start
        # 阶段 3.6 标记为 legacy, 计划在 3.7 删除
        try:
            import httpx
            import asyncio
            async def _start_worker():
                async with httpx.AsyncClient() as client:
                    await client.post("http://localhost:8000/api/worker/start")
            asyncio.create_task(_start_worker())
        except Exception:
            pass  # Worker 启动是 best-effort

    return {"ok": True, "data": result}
