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

# Chinese: "第N章" with optional whitespace between EVERY token.
# The old regex was `^\s*第([零〇...0-9]+)章[...]*(.{0,80})` which
# required the digit to be glued to 「第」 with no whitespace — the
# common case is "第 1 章 起点" (space after 第) and that never
# matched, so every upload fell back to the single-chapter "全文"
# path. The fix: optional \s* between 第, the number, 章, and the
# title.
_CN_CHAPTER_RE = re.compile(
    r"^\s*第\s*([零〇一二三四五六七八九十百千万0-9]+)\s*章[\s　\.：:—\-]*(.{0,80})$",
    re.MULTILINE,
)
# English: "Chapter 1" / "Chapter 1: Foo" / "CHAPTER ONE" / "Chapter One"
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


@router.post("/materials/upload/batch")
async def upload_materials_batch(
    files: list[UploadFile] = File(...),
    auto_chapterize: bool = Form(default=True),
    min_chapter_chars: int = Form(default=200),
    db: AsyncSession = Depends(get_db),
):
    """R19: accept up to 5 books in a single multipart POST.

    Each file is parsed with the same per-format dispatch as the
    single-file upload route; each resulting material is then
    auto-chapterized in-place so the user lands on a populated
    library without an extra click. Per-file failures are surfaced
    in the response as ``{"ok": false, "error": ...}`` and the
    whole batch still returns 200 — we don't want one bad EPUB
    to nuke 4 successful TXT uploads.

    The 5-file cap is enforced in the route (the frontend also
    mirrors it via the ``<input multiple>`` limit).

    No ``response_model`` — the per-entry shape is mixed (success
    returns ``{ok, data: StudyMaterialRead}``, failure returns
    ``{ok: false, filename, error}``), so we let the dict go out
    untyped and the client treats each entry by its own ``ok``.
    """
    if not files:
        raise bad_request("至少选择一个文件。")
    if len(files) > 5:
        raise bad_request(f"批量上传最多 5 个文件,收到 {len(files)}。")
    results: list[dict[str, Any]] = []
    for f in files:
        try:
            content = await f.read()
            if len(content) > 32 * 1024 * 1024:
                raise ValueError("文件过大 (>32MB)。")
            title = (f.filename or "upload").rsplit(".", 1)[0]
            raw = _extract_text_from_upload(f.filename or "upload.txt", content)
            if not raw or not raw.strip():
                raise ValueError("文件解析后没有可识别的正文。")
            row = StudyMaterial(
                title=title,
                author="",
                source="upload",
                raw_text=raw,
                status="draft" if raw else "empty",
            )
            db.add(row)
            await db.flush()
            entry: dict[str, Any] = {
                "ok": True,
                "data": {
                    "id": row.id,
                    "project_id": row.project_id,
                    "title": row.title,
                    "author": row.author,
                    "source": row.source,
                    "status": row.status,
                    "error": row.error,
                    "chapter_count": row.chapter_count or 0,
                    "character_count": row.character_count or 0,
                    "raw_text_length": len(row.raw_text or ""),
                    "extra": row.extra,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                },
            }
            if auto_chapterize and row.raw_text:
                try:
                    chunks = _split_chapters(row.raw_text, pattern="auto")
                    created = 0
                    if chunks:
                        for idx, t, body in chunks:
                            if len(body) < min_chapter_chars:
                                continue
                            # Use a direct INSERT instead of
                            # ``row.chapters.append(StudyChapter(...))``
                            # — appending onto a relationship triggers
                            # a lazy-load of the collection on first
                            # access, and that lazy load is sync-IO
                            # inside an async session (greenlet error).
                            # Inserting the chapter row directly with
                            # ``material_id`` sidesteps the relationship
                            # walk entirely.
                            db.add(StudyChapter(
                                material_id=row.id,
                                chapter_index=idx,
                                title=t,
                                content=body,
                                char_count=len(body),
                            ))
                            created += 1
                        # Flush so the new chapter rows reach the DB
                        # before the response serialises chapter_count.
                        await db.flush()
                    row.chapter_count = created
                    row.status = "ready" if created else "draft"
                    # One more flush to push chapter_count + status
                    # back to the DB and update the in-memory row
                    # attributes that we read on the next two lines.
                    await db.flush()
                except Exception as exc:
                    entry["chapterize_error"] = str(exc)
            # Reflect the post-chapterize values back into the entry
            # so the client gets the final chapter_count + status
            # without an extra GET.
            entry["data"]["chapter_count"] = row.chapter_count or 0
            entry["data"]["status"] = row.status
            results.append(entry)
        except Exception as exc:
            results.append({
                "ok": False,
                "filename": f.filename,
                "error": f"{exc.__class__.__name__}: {exc}".strip(),
            })
    return {"ok": True, "data": results}


@router.post("/materials/upload", response_model=APIResponse[StudyMaterialRead])
async def upload_material(
    title: str = Form(...),
    author: str = Form(""),
    project_id: int | None = Form(default=None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[StudyMaterialRead]:
    """Accept a book upload and create the material row with its body.

    R18 / P0-STUDY-3: supports a much wider set of formats than the
    original ``.txt`` only path. The list is
    ``.txt / .md / .pdf / .docx / .html / .htm / .epub``.

    Multipart route — the file's bytes are decoded/parsed into
    ``raw_text`` (the MVP doesn't keep an on-disk copy; if the user
    wants a smaller payload for chapterize, they can re-paste).

    The file extension is matched case-insensitively; the file body
    is parsed lazily inside ``_extract_text_from_upload`` so a
    missing optional dep degrades gracefully (one format becomes
    unavailable, not the whole endpoint).
    """
    raw_bytes = await file.read()
    if len(raw_bytes) > 32 * 1024 * 1024:
        # 32 MB hard cap. PDF/DOCX can be big and parsing them into
        # raw_text balloons memory. Above this we refuse rather than
        # OOM the worker. User can split their book or paste chunks.
        raise HTTPException(status_code=413, detail="文件过大 (>32MB),请拆开上传或粘贴正文。")
    filename = file.filename or "upload.txt"
    try:
        raw = _extract_text_from_upload(filename, raw_bytes)
    except ValueError as exc:
        raise bad_request(str(exc)) from exc
    except Exception as exc:
        # Don't leak the underlying stack to the user; they get a
        # clean message and the failure is in the worker log.
        raise HTTPException(
            status_code=400,
            detail=f"解析文件失败: {exc.__class__.__name__}: {exc}".strip(),
        ) from exc
    if not raw or not raw.strip():
        raise bad_request("文件解析后没有可识别的正文。")
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


# -------------------- R18 / P0-STUDY-3: file -> text --------------------

# Map lower-cased file extension -> parser key. Anything not in this
# map is rejected up front (cheaper than running a parser that
# would just produce empty text). Keep it in one place so the
# frontend can mirror the same list when building the <input accept>.
_SUPPORTED_EXTS: dict[str, str] = {
    ".txt":  "txt",
    ".md":   "md",
    ".markdown": "md",
    ".pdf":  "pdf",
    ".docx": "docx",
    ".doc":  "docx-legacy",  # legacy .doc → not supported; surface a clear error
    ".html": "html",
    ".htm":  "html",
    ".epub": "epub",
}


def _extract_text_from_upload(filename: str, content: bytes) -> str:
    """Dispatch by extension. Return a plain ``str`` of the book body.

    Imports the heavy parsing libs lazily so a single missing
    optional dep doesn't break the whole endpoint — only the one
    format that needs it.
    """
    name = (filename or "").strip()
    if not name:
        raise ValueError("文件名不能为空。")
    ext = ""
    for candidate in (".epub", ".docx", ".html", ".htm", ".pdf", ".md",
                      ".markdown", ".doc", ".txt"):
        if name.lower().endswith(candidate):
            ext = candidate
            break
    if not ext or ext not in _SUPPORTED_EXTS:
        allowed = ", ".join(sorted(_SUPPORTED_EXTS))
        raise ValueError(f"暂不支持的格式: {ext or '?'}. 接受: {allowed}")
    kind = _SUPPORTED_EXTS[ext]
    if kind == "txt":
        return _parse_txt(content)
    if kind == "md":
        # Markdown is a superset of plain text for our purposes;
        # we just strip HTML-ish tags if any. The chapter splitter
        # doesn't care about ``**bold**`` etc.
        return _parse_txt(content)
    if kind == "pdf":
        return _parse_pdf(content)
    if kind == "docx":
        return _parse_docx(content)
    if kind == "docx-legacy":
        raise ValueError(
            "旧版 .doc (二进制) 不直接支持 — 请在 Word 里另存为 .docx 后再上传。"
        )
    if kind == "html":
        return _parse_html(content)
    if kind == "epub":
        return _parse_epub(content)
    raise ValueError(f"无法识别的格式: {ext}")


def _parse_txt(content: bytes) -> str:
    return content.decode("utf-8", errors="replace")


def _parse_pdf(content: bytes) -> str:
    import io
    import pypdf  # lazy import

    reader = pypdf.PdfReader(io.BytesIO(content))
    parts: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text:
            parts.append(text)
    if not parts:
        raise ValueError("PDF 解析后没有可识别的文字 (可能为扫描版/纯图片)。")
    return "\n\n".join(parts)


def _parse_docx(content: bytes) -> str:
    import io
    import docx  # python-docx, lazy import

    document = docx.Document(io.BytesIO(content))
    parts: list[str] = []
    for p in document.paragraphs:
        if p.text:
            parts.append(p.text)
    # Include text from tables too — lots of novels on 网文导出 have
    # character stats in the front matter. Joining with newlines is
    # fine; the chapter splitter is robust to extra newlines.
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text:
                    parts.append(cell.text)
    if not parts:
        raise ValueError("DOCX 解析后没有可识别的正文。")
    return "\n".join(parts)


def _parse_html(content: bytes) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(content, "lxml")
    # Drop script / style entirely — they were never text we want.
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    # Pull out <br> as newline-ish separators so paragraphs don't
    # collapse into a single wall of text. Block-level tags will
    # naturally get their own newlines via get_text's separator.
    text = soup.get_text(separator="\n")
    # Collapse runs of 3+ blank lines (very common in scraped HTML).
    import re as _re
    text = _re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_epub(content: bytes) -> str:
    """EPUB is a zip of XHTML files. Walk the spine and concatenate.

    The user gets a single string back with each ``<p>`` separated
    by a blank line, which is what our chapter splitter expects.
    """
    import io
    import os
    import tempfile
    import zipfile
    from bs4 import BeautifulSoup

    # ebooklib.epub.read_epub insists on a real path or file-like
    # with a real ``.name`` attribute. The cleanest portable path
    # is to write to a tempfile once and feed that path. We try
    # the clean path first and fall back to raw zipfile walk if
    # ebooklib is missing.
    try:
        import ebooklib  # type: ignore
        from ebooklib import epub

        with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            book = epub.read_epub(tmp_path)
            items = [
                it for it in book.get_items()
                if it.get_type() == ebooklib.ITEM_DOCUMENT
            ]
            parts: list[str] = []
            for it in items:
                html = it.get_content() or b""
                soup = BeautifulSoup(html, "lxml")
                for tag in soup(["script", "style"]):
                    tag.decompose()
                text = soup.get_text(separator="\n").strip()
                if text:
                    parts.append(text)
            if not parts:
                raise ValueError("EPUB 解析后没有可识别的正文。")
            return "\n\n".join(parts)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except ImportError:
        # ebooklib missing → fall back to raw zipfile walk.
        import re as _re
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            members = [
                n for n in zf.namelist()
                if _re.search(r"\.x?html?$", n, _re.IGNORECASE)
            ]
            members = sorted(members)
            parts = []
            for m in members:
                html = zf.read(m)
                soup = BeautifulSoup(html, "lxml")
                for tag in soup(["script", "style"]):
                    tag.decompose()
                text = soup.get_text(separator="\n").strip()
                if text:
                    parts.append(text)
            if not parts:
                raise ValueError("EPUB 解析后没有可识别的正文。")
            return "\n\n".join(parts)


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
