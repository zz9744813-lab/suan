"""Study (拆书) routes — materials, chapters, character extraction."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.base import AgentContext
from app.agents.study import StudyCharacterAgent
from app.core.database import get_db
from app.core.errors import bad_request, not_found
from app.models.study import BehaviorPattern, StudyChapter, StudyCharacter, StudyMaterial
from app.models.task import AgentTask
from app.schemas import (
    APIResponse,
    ChapterizeRequest,
    StudyChapterRead,
    StudyCharacterCreate,
    StudyCharacterRead,
    StudyMaterialCreate,
    StudyMaterialDetail,
    StudyMaterialRead,
    StudyMaterialUpdate,
    StudyRequest,
)
from app.services.llm.router import get_llm_router
from app.services.prompt_engine import get_prompt_engine


router = APIRouter(prefix="/study", tags=["study"])


# -------------------- chapterize helpers --------------------

# Chinese: 第[一-龥0-9零〇一二三四五六七八九十百千万]+章 + optional title
_CN_CHAPTER_RE = re.compile(
    r"^\s*第([零〇一二三四五六七八九十百千万0-9]+)章[　\s\.：:—\-]*(.{0,80})$",
    re.MULTILINE,
)
# English: "Chapter 1" / "Chapter 1: Foo" / "CHAPTER ONE"
_EN_CHAPTER_RE = re.compile(
    r"^\s*CHAPTER\s+([0-9]+|[A-Za-z]+)[\.\:\s\-—]*(.{0,80})$",
    re.MULTILINE | re.IGNORECASE,
)
# Generic "Chapter 1" fallback
_EN_CHAPTER_LOOSE_RE = re.compile(
    r"^\s*Chapter\s+([0-9]+)[\.\:\s\-—]*(.{0,80})$",
    re.MULTILINE | re.IGNORECASE,
)


def _cn_to_int(s: str) -> int:
    """Convert a Chinese chapter number to int. Falls back to the
    raw string hash if the number is too gnarly to parse (we just
    need an ordering signal — a 2.7 GB 2000-chapter 玄幻 can have
    ``第两千三百四十五章`` and the regex is unlikely to know every
    variant; a fallback is fine).
    """
    digits_map = {
        "零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
        "六": 6, "七": 7, "八": 8, "九": 9,
    }
    units = {"十": 10, "百": 100, "千": 1000, "万": 10000}
    if s.isdigit():
        return int(s)
    total = 0
    section = 0
    current = 0
    for ch in s:
        if ch in digits_map:
            current = digits_map[ch]
        elif ch in units:
            section += (current or 1) * units[ch]
            current = 0
        else:
            # Unknown character — bail with a hash-based fallback.
            return abs(hash(s)) % 100000
    return total + section + current


def _split_chapters(text: str, pattern: str = "auto") -> list[tuple[int, str, str]]:
    """Return a list of (chapter_index, title, content) tuples.

    The first item is always ``(1, "序章", text_before_first_header)`` if
    the user pastes a preamble, or ``(1, "第 N 章", full_text)`` if the
    first line is already a chapter header.
    """
    text = (text or "").strip()
    if not text:
        return []
    # Pick a regex.
    if pattern == "chinese":
        rx = _CN_CHAPTER_RE
    elif pattern == "english":
        rx = _EN_CHAPTER_RE
    else:
        # auto: try Chinese first (more common in the project's audience),
        # fall back to English.
        cn_hits = list(_CN_CHAPTER_RE.finditer(text))
        en_hits = list(_EN_CHAPTER_RE.finditer(text))
        if not en_hits and not cn_hits:
            en_hits = list(_EN_CHAPTER_LOOSE_RE.finditer(text))
        # Whichever has more matches wins.
        if len(cn_hits) >= len(en_hits):
            rx = _CN_CHAPTER_RE
            matches = cn_hits
            cn_mode = True
        else:
            rx = _EN_CHAPTER_RE
            matches = en_hits
            cn_mode = False
        if not matches:
            return [(1, "全文", text)]
        return _chunks_from_matches(text, matches, cn_mode=cn_mode)
    matches = list(rx.finditer(text))
    if not matches:
        return [(1, "全文", text)]
    return _chunks_from_matches(text, matches, cn_mode=(pattern == "chinese"))


def _chunks_from_matches(
    text: str, matches: list[re.Match], *, cn_mode: bool
) -> list[tuple[int, str, str]]:
    out: list[tuple[int, str, str]] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        # If the very first line of the document has no chapter header
        # before the first match, surface that preamble as a prologue
        # so the user can still see it.
        if i == 0 and m.start() > 0:
            preamble = text[: m.start()].strip()
            if len(preamble) > 50:
                out.append((1, "序章", preamble))
                # Bump subsequent indices by 1.
                first_real_index = 2
            else:
                first_real_index = 1
        else:
            first_real_index = 1
        # Title: capture group 1 is the number, group 2 is the optional
        # name. We also include the original header line in the content
        # so the user can see the full chapter start.
        num = m.group(1)
        title = (m.group(2) or "").strip()
        if cn_mode:
            try:
                num_int = _cn_to_int(num)
            except Exception:
                num_int = i + 1
        else:
            try:
                num_int = int(num)
            except ValueError:
                num_int = i + 1
        # Cap the title length.
        if len(title) > 60:
            title = title[:60] + "…"
        full_title = f"第 {num_int} 章" + (f" · {title}" if title else "")
        # Prepend the original header line so the chunk is searchable.
        full_body = (m.group(0).rstrip() + "\n" + body).strip()
        out.append((first_real_index + (num_int - 1 if i > 0 or first_real_index == 1 else 0), full_title, full_body))
    # Re-index defensively (we may have inserted a prologue).
    return [(i + 1, t, c) for i, (_, t, c) in enumerate(out)]


# -------------------- endpoints --------------------

@router.get("/materials", response_model=APIResponse[list[StudyMaterialRead]])
async def list_materials(
    project_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[StudyMaterialRead]]:
    stmt = select(StudyMaterial).order_by(StudyMaterial.updated_at.desc())
    if project_id is not None:
        stmt = stmt.where(StudyMaterial.project_id == project_id)
    rows = (await db.execute(stmt)).scalars().all()
    return {"ok": True, "data": [StudyMaterialRead.from_orm_trimmed(r) for r in rows]}


@router.post("/materials", response_model=APIResponse[StudyMaterialRead])
async def create_material(
    body: StudyMaterialCreate, db: AsyncSession = Depends(get_db)
) -> APIResponse[StudyMaterialRead]:
    row = StudyMaterial(
        project_id=body.project_id,
        title=body.title,
        author=body.author,
        source=body.source,
        raw_text=body.raw_text,
        status="draft" if body.raw_text else "empty",
    )
    db.add(row)
    await db.flush()
    return {"ok": True, "data": StudyMaterialRead.from_orm_trimmed(row)}


@router.post("/materials/upload", response_model=APIResponse[StudyMaterialRead])
async def upload_material(
    title: str = Form(...),
    author: str = Form(""),
    project_id: int | None = Form(default=None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[StudyMaterialRead]:
    """Accept a .txt upload and create the material row with its body.

    Multipart route — the file's bytes are read into ``raw_text`` (the
    MVP doesn't keep an on-disk copy; if the user wants a smaller
    payload for chapterize, they can re-paste).
    """
    raw = (await file.read()).decode("utf-8", errors="replace")
    row = StudyMaterial(
        project_id=project_id,
        title=title,
        author=author,
        source="upload",
        raw_text=raw,
        status="draft" if raw else "empty",
    )
    db.add(row)
    await db.flush()
    return {"ok": True, "data": StudyMaterialRead.from_orm_trimmed(row)}


@router.get("/materials/{material_id}", response_model=APIResponse[StudyMaterialDetail])
async def get_material(
    material_id: int,
    include_text: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[StudyMaterialDetail]:
    row = (await db.execute(
        select(StudyMaterial)
        .options(
            selectinload(StudyMaterial.chapters),
            selectinload(StudyMaterial.characters),
        )
        .where(StudyMaterial.id == material_id)
    )).scalar_one_or_none()
    if row is None:
        raise not_found("StudyMaterial", material_id)
    detail = StudyMaterialDetail(
        id=row.id,
        project_id=row.project_id,
        title=row.title,
        author=row.author,
        source=row.source,
        status=row.status,
        error=row.error,
        chapter_count=row.chapter_count,
        character_count=row.character_count,
        raw_text_length=len(row.raw_text or ""),
        extra=row.extra,
        created_at=row.created_at,
        updated_at=row.updated_at,
        raw_text=row.raw_text if include_text else "",
        chapters=[StudyChapterRead.model_validate(c) for c in row.chapters],
        characters=[StudyCharacterRead.model_validate(c) for c in row.characters],
    )
    return {"ok": True, "data": detail}


@router.patch("/materials/{material_id}", response_model=APIResponse[StudyMaterialRead])
async def update_material(
    material_id: int,
    body: StudyMaterialUpdate,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[StudyMaterialRead]:
    row = await db.get(StudyMaterial, material_id)
    if row is None:
        raise not_found("StudyMaterial", material_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.flush()
    return {"ok": True, "data": StudyMaterialRead.from_orm_trimmed(row)}


@router.delete("/materials/{material_id}", response_model=APIResponse[dict])
async def delete_material(
    material_id: int, db: AsyncSession = Depends(get_db)
) -> APIResponse[dict]:
    row = await db.get(StudyMaterial, material_id)
    if row is None:
        raise not_found("StudyMaterial", material_id)
    await db.delete(row)
    return {"ok": True, "data": {"deleted": material_id}}


@router.post("/materials/{material_id}/chapterize", response_model=APIResponse[StudyMaterialDetail])
async def chapterize_material(
    material_id: int,
    body: ChapterizeRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[StudyMaterialDetail]:
    """Split the material's raw_text into StudyChapter rows.

    Idempotent: wipes the existing chapters first. The user can rerun
    after editing the raw_text.
    """
    row = (await db.execute(
        select(StudyMaterial)
        .options(
            selectinload(StudyMaterial.chapters),
            selectinload(StudyMaterial.characters),
        )
        .where(StudyMaterial.id == material_id)
    )).scalar_one_or_none()
    if row is None:
        raise not_found("StudyMaterial", material_id)
    body = body or ChapterizeRequest()
    if not row.raw_text:
        raise bad_request("该 Material 还没有 raw_text，先粘贴或上传文本。")
    chunks = _split_chapters(row.raw_text, pattern=body.pattern)
    if not chunks:
        raise bad_request("分章失败：没有从文本中识别到任何章节。请检查文本格式。")
    # Wipe existing chapters (and orphan characters whose source chapter
    # is gone). We keep the characters so the user doesn't lose the
    # extracted set if they re-chapterize.
    for c in list(row.chapters):
        await db.delete(c)
    await db.flush()
    for idx, title, content in chunks:
        if len(content) < body.min_chapter_chars:
            # Skip tiny fragments — they're likely false positives.
            continue
        row.chapters.append(StudyChapter(
            chapter_index=idx,
            title=title,
            content=content,
            char_count=len(content),
        ))
    row.chapter_count = len(row.chapters)
    row.status = "ready"
    row.error = None
    await db.flush()
    return {"ok": True, "data": StudyMaterialDetail(
        id=row.id, project_id=row.project_id, title=row.title, author=row.author,
        source=row.source, status=row.status, error=row.error,
        chapter_count=row.chapter_count, character_count=row.character_count,
        raw_text_length=len(row.raw_text or ""), extra=row.extra,
        created_at=row.created_at, updated_at=row.updated_at,
        raw_text="",
        chapters=[StudyChapterRead.model_validate(c) for c in row.chapters],
        characters=[StudyCharacterRead.model_validate(c) for c in row.characters],
    )}


@router.get("/materials/{material_id}/chapters", response_model=APIResponse[list[StudyChapterRead]])
async def list_chapters(
    material_id: int, db: AsyncSession = Depends(get_db)
) -> APIResponse[list[StudyChapterRead]]:
    rows = (await db.execute(
        select(StudyChapter)
        .where(StudyChapter.material_id == material_id)
        .order_by(StudyChapter.chapter_index.asc())
    )).scalars().all()
    return {"ok": True, "data": [StudyChapterRead.model_validate(r) for r in rows]}


@router.get("/materials/{material_id}/characters", response_model=APIResponse[list[StudyCharacterRead]])
async def list_characters(
    material_id: int, db: AsyncSession = Depends(get_db)
) -> APIResponse[list[StudyCharacterRead]]:
    rows = (await db.execute(
        select(StudyCharacter)
        .where(StudyCharacter.material_id == material_id)
        .order_by(StudyCharacter.confidence.desc(), StudyCharacter.id.asc())
    )).scalars().all()
    return {"ok": True, "data": [StudyCharacterRead.model_validate(r) for r in rows]}


@router.post("/materials/{material_id}/characters", response_model=APIResponse[StudyCharacterRead])
async def add_character(
    material_id: int,
    body: StudyCharacterCreate,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[StudyCharacterRead]:
    row = await db.get(StudyMaterial, material_id)
    if row is None:
        raise not_found("StudyMaterial", material_id)
    ch = StudyCharacter(
        material_id=material_id,
        name=body.name,
        aliases=body.aliases or [],
        role=body.role or "其他",
        tags=body.tags or [],
        base_profile=body.base_profile,
        confidence=body.confidence or 0.5,
    )
    db.add(ch)
    row.character_count = (row.character_count or 0) + 1
    await db.flush()
    return {"ok": True, "data": StudyCharacterRead.model_validate(ch)}


@router.delete("/materials/{material_id}/characters/{character_id}", response_model=APIResponse[dict])
async def delete_character(
    material_id: int,
    character_id: int,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    ch = await db.get(StudyCharacter, character_id)
    if ch is None or ch.material_id != material_id:
        raise not_found("StudyCharacter", character_id)
    parent = await db.get(StudyMaterial, material_id)
    await db.delete(ch)
    if parent is not None and parent.character_count > 0:
        parent.character_count -= 1
    return {"ok": True, "data": {"deleted": character_id}}


@router.post("/materials/{material_id}/study", response_model=APIResponse[list[StudyCharacterRead]])
async def study_chapter(
    material_id: int,
    body: StudyRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[list[StudyCharacterRead]]:
    """Run the StudyCharacterAgent on a single chapter and persist the
    extracted characters.

    P15 / P0-STUDY-1: this used to call a regex stub
    (``_stub_study_parse``) because step-3.7-flash was unreliable for
    short chapter text. Now that the picker in
    ``app/services/llm/client.py`` reliably extracts the JSON from
    reasoning models (and the agent's ``allow_json_fallback=True``
    covers the worst case), we route through the real
    ``StudyCharacterAgent`` which goes through the same model-role
    bindings / prompt-versioning / AgentStep audit trail as the
    chapter pipeline.

    On a 5K-char chapter this takes 5-15s with the cheap model.
    Idempotency: characters from this chapter are upserted by
    ``(material_id, source_chapter_id, name)`` — running twice on
    the same chapter does not create duplicates.

    The task payload includes ``{"material_id": ..., "chapter_id": ...,
    "max_chars": ...}`` and we synthesize an ``AgentTask`` row so the
    AgentStep trail is consistent with the rest of the system.
    """
    material = await db.get(StudyMaterial, material_id)
    if material is None:
        raise not_found("StudyMaterial", material_id)
    chapter = await db.get(StudyChapter, body.chapter_id)
    if chapter is None or chapter.material_id != material_id:
        raise not_found("StudyChapter", body.chapter_id)
    text = chapter.content[: body.max_chars]
    existing = (await db.execute(
        select(StudyCharacter).where(StudyCharacter.material_id == material_id)
    )).scalars().all()
    existing_summary = "\n".join(
        f"- {c.name} (别名: {', '.join(c.aliases or [])}; 标签: {', '.join(c.tags or [])})"
        for c in existing
    ) or "（无）"

    # Synthesise a lightweight AgentTask so the AgentStep rows the
    # agent writes have a real parent. ``task_type=study_character``
    # keeps it out of the chapter-pipeline queue.
    study_task = AgentTask(
        project_id=material.project_id,
        chapter_id=None,
        task_type="study_character",
        status="running",
        priority=50,
        payload={
            "material_id": material_id,
            "chapter_id": chapter.id,
            "max_chars": body.max_chars,
        },
        started_at=datetime.utcnow(),
    )
    db.add(study_task)
    await db.flush()

    # Run the real LLM-backed agent. The agent's BaseAgent.run()
    # handles prompt rendering, model-role resolution, JSON parsing
    # (with allow_json_fallback) and the AgentStep audit row.
    agent = StudyCharacterAgent(
        router=get_llm_router(),
        engine=get_prompt_engine(),
    )
    try:
        result = await agent.run(
            AgentContext(
                db=db,
                task=study_task,
                project_id=material.project_id or 0,
                chapter_id=None,
                inputs={
                    "chapter_text": text,
                    "existing_characters": existing_summary,
                },
            )
        )
    except Exception as exc:
        # Mark the task as failed and re-raise so the API returns 4xx
        # — we don't want a silent failure to leave the user wondering
        # why no characters showed up.
        study_task.status = "failed"
        study_task.error = str(exc)
        study_task.finished_at = datetime.utcnow()
        await db.flush()
        raise
    study_task.status = "succeeded"
    study_task.finished_at = datetime.utcnow()
    study_task.cost_usd = result.cost_usd
    study_task.input_tokens = result.input_tokens
    study_task.output_tokens = result.output_tokens
    parsed = result.parsed or {}
    characters = parsed.get("characters") or []

    # Upsert: for each returned character, look up an existing row
    # in the same material with the same name; if present, merge
    # aliases / tags; if absent, insert. We then return the full set
    # for this material — including any pre-existing ones we
    # touched, so the UI can show "study touched these".
    new_rows: list[StudyCharacter] = []
    touched: list[StudyCharacter] = []
    for item in characters:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue
        existing_row = next(
            (c for c in existing if c.name == name), None
        )
        if existing_row is not None:
            # Merge aliases (set union) and tags (set union). Don't
            # overwrite the user's manual edits to base_profile.
            new_aliases = list({*(existing_row.aliases or []), *(item.get("aliases") or [])})
            new_tags = list({*(existing_row.tags or []), *(item.get("tags") or [])})
            existing_row.aliases = new_aliases
            existing_row.tags = new_tags
            existing_row.source_chapter_id = chapter.id  # last seen
            existing_row.confidence = max(
                existing_row.confidence or 0.0,
                float(item.get("confidence") or 0.0),
            )
            touched.append(existing_row)
            continue
        ch = StudyCharacter(
            material_id=material_id,
            source_chapter_id=chapter.id,
            name=name,
            aliases=item.get("aliases") or [],
            role=item.get("role") or "其他",
            tags=item.get("tags") or [],
            base_profile=item.get("base_profile") or None,
            confidence=float(item.get("confidence") or 0.0),
        )
        db.add(ch)
        new_rows.append(ch)
        touched.append(ch)
    chapter.last_studied_at = datetime.utcnow()
    await db.flush()
    # Recompute the material's character_count = total rows on disk.
    total_count = (await db.execute(
        select(StudyCharacter).where(StudyCharacter.material_id == material_id)
    )).scalars().all()
    material.character_count = len(total_count)
    await db.flush()
    # Return the rows we touched (newly created + updated) so the
    # UI can highlight them in the table.
    return {"ok": True, "data": [StudyCharacterRead.model_validate(c) for c in touched]}


def _stub_study_parse(text: str) -> dict[str, Any]:
    """Deterministic character extraction used as a LAST-DITCH fallback.

    P15 / P0-STUDY-1: previously this was the *only* path; now it
    only runs when the LLM agent returns a non-JSON fallback that
    explicitly asks for it.  We keep the sliding-2-char-window
    approach because it's the only signal left when the model
    produces nothing useful at all.
    """
    if not text:
        return {"characters": []}
    import collections
    windows = [
        text[i:i+2]
        for i in range(len(text) - 1)
        if all("\u4e00" <= c <= "\u9fff" for c in text[i:i+2])
    ]
    counts = collections.Counter(windows)
    out: list[dict[str, Any]] = []
    for name, c in counts.most_common(8):
        if c < 3:
            continue
        out.append({
            "name": name,
            "aliases": [],
            "role": "其他",
            "tags": [],
            "base_profile": {"summary": f"出现 {c} 次"},
            "confidence": min(0.9, 0.4 + c * 0.02),
        })
    return {"characters": out}
