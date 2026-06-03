"""Global search (Round 11, P0-UI-5).

Searches across all the entity types a user might want to find from
a single query box:

  - projects        (name / description / category)
  - chapters        (title)
  - memory chars    (name / aliases / tags / base_profile)
  - memory foreshadows (name / summary / related_*)
  - memory hard facts (fact / category)
  - study materials (title / author)
  - behavior patterns (name / tags / behavior / dialogue / scene / risks)

We don't try to be a full-text engine — SQLite FTS5 would be the right
tool for a bigger project. For our scale (a handful of projects, low
thousands of characters / foreshadows), a simple in-memory substring
scan with case-insensitive matching is fast enough and avoids the
FTS5 migration dance.

Each result has the shape:

  {
    "type":   "project" | "chapter" | "character" | "foreshadow"
            | "hard_fact" | "study_material" | "behavior_pattern",
    "id":     <int>,
    "title":  <str>,            # primary display text
    "snippet":<str>,            # short excerpt with hit context
    "link":   <str>,            # relative URL the UI should navigate to
    "score":  <int>,            # higher = better match
  }

The router returns a flat list ordered by score desc, capped at 50.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.memory import MemoryCharacter, MemoryForeshadow, MemoryHardFact
from app.models.project import Chapter, Project
from app.models.study import StudyMaterial, BehaviorPattern


router = APIRouter(prefix="/search", tags=["search"])


_MAX_RESULTS = 50


def _hit(text: str | None, q: str) -> tuple[bool, int]:
    """Return (matched, score) for a single string. Score is +1 per hit."""
    if not text or not q:
        return False, 0
    ql = q.lower()
    tl = text.lower()
    if ql in tl:
        # length-weighted — shorter texts with a hit are usually a
        # better target (e.g. character name vs long description)
        return True, max(1, 60 - min(60, len(tl)))
    return False, 0


def _snippet(text: str | None, q: str, width: int = 80) -> str:
    """Return a short excerpt with the first hit highlighted-ish.

    We don't emit HTML — the UI does its own highlighting. We just
    want a 1-line preview for the dropdown.
    """
    if not text:
        return ""
    ql = q.lower()
    tl = text.lower()
    idx = tl.find(ql)
    if idx < 0:
        return text[:width] + ("…" if len(text) > width else "")
    start = max(0, idx - width // 3)
    end = min(len(text), idx + len(q) + width - (idx - start))
    return ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")


def _any_match(obj: Any, fields: list[str], q: str) -> tuple[int, str]:
    """Walk the listed fields on `obj`, sum the hit scores, return
    (score, first non-empty hit text used for snippet)."""
    total = 0
    snippet_src = ""
    for f in fields:
        v = getattr(obj, f, None)
        if isinstance(v, (list, dict)):
            # list/dict fields (aliases, tags, base_profile): serialise
            # to a search blob, but prefer the string fields first by
            # weighting them less
            v = " ".join(str(x) for x in v) if isinstance(v, list) else " ".join(f"{k}={val}" for k, val in v.items())
        hit, score = _hit(v, q)
        if hit and not snippet_src:
            snippet_src = str(v)
        total += score
    return total, snippet_src


@router.get("")
async def search(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    # Empty / whitespace-only queries return immediately. We DO allow
    # 1-char queries (CJK names like "林" / "玉" are common and the
    # substring scan is cheap).
    if not q.strip():
        return {"ok": True, "data": [], "q": q, "total": 0}

    ql = q.lower()
    results: list[dict[str, Any]] = []

    # ---- projects ----
    projects = (await db.execute(select(Project))).scalars().all()
    for p in projects:
        score, snippet_src = _any_match(p, ["name", "description", "category", "genre"], q)
        if score > 0 or ql in (p.name or "").lower():
            # Give name hits an explicit boost
            if ql in (p.name or "").lower():
                score += 100
            results.append({
                "type": "project",
                "id": p.id,
                "title": p.name,
                "snippet": _snippet(snippet_src or p.description or p.category, q),
                "link": f"/projects/{p.id}",
                "score": score,
            })

    # ---- chapters ----
    chapters = (await db.execute(select(Chapter))).scalars().all()
    for c in chapters:
        if ql in (c.title or "").lower():
            results.append({
                "type": "chapter",
                "id": c.id,
                "title": f"第 {c.chapter_no} 章 · {c.title}",
                "snippet": _snippet(c.title, q),
                "link": f"/projects/{c.project_id}/chapters/{c.id}",
                "score": 90 + len(c.title or ""),
            })

    # ---- memory characters ----
    chars = (await db.execute(select(MemoryCharacter))).scalars().all()
    for c in chars:
        score, snippet_src = _any_match(
            c, ["name", "role"], q,
        )
        # aliases, tags, base_profile: sum as 1
        for fld in ("aliases", "tags"):
            v = getattr(c, fld, None) or []
            joined = " ".join(str(x) for x in v)
            hit, s = _hit(joined, q)
            if hit:
                score += s
                if not snippet_src:
                    snippet_src = joined
        bp = c.base_profile or {}
        if isinstance(bp, dict):
            bp_str = " ".join(f"{k}={v}" for k, v in bp.items())
            hit, s = _hit(bp_str, q)
            if hit:
                score += s
                if not snippet_src:
                    snippet_src = bp_str
        if ql in (c.name or "").lower():
            score += 80
        if score > 0:
            results.append({
                "type": "character",
                "id": c.id,
                "title": c.name,
                "snippet": _snippet(snippet_src, q),
                "link": f"/memory?project={c.project_id}",
                "score": score,
            })

    # ---- memory foreshadows ----
    foreshadows = (await db.execute(select(MemoryForeshadow))).scalars().all()
    for f in foreshadows:
        score, snippet_src = _any_match(f, ["name", "summary", "related_main_plot"], q)
        for fld in ("related_characters", "related_items"):
            v = getattr(f, fld, None) or []
            joined = " ".join(str(x) for x in v)
            hit, s = _hit(joined, q)
            if hit:
                score += s
                if not snippet_src:
                    snippet_src = joined
        if ql in (f.name or "").lower():
            score += 70
        if score > 0:
            results.append({
                "type": "foreshadow",
                "id": f.id,
                "title": f.name,
                "snippet": _snippet(snippet_src, q),
                "link": f"/memory?project={f.project_id}",
                "score": score,
            })

    # ---- memory hard facts ----
    facts = (await db.execute(select(MemoryHardFact))).scalars().all()
    for hf in facts:
        score, snippet_src = _any_match(hf, ["fact", "category"], q)
        if ql in (hf.fact or "").lower():
            score += 50
        if score > 0:
            results.append({
                "type": "hard_fact",
                "id": hf.id,
                "title": f"[{hf.category}] {hf.fact[:40]}{'…' if len(hf.fact) > 40 else ''}",
                "snippet": _snippet(hf.fact, q),
                "link": f"/memory?project={hf.project_id}",
                "score": score,
            })

    # ---- study materials ----
    materials = (await db.execute(select(StudyMaterial))).scalars().all()
    for m in materials:
        score, snippet_src = _any_match(m, ["title", "author"], q)
        if ql in (m.title or "").lower():
            score += 60
        if score > 0:
            results.append({
                "type": "study_material",
                "id": m.id,
                "title": m.title,
                "snippet": _snippet(snippet_src, q),
                "link": "/study",
                "score": score,
            })

    # ---- behavior patterns ----
    patterns = (await db.execute(select(BehaviorPattern))).scalars().all()
    for p in patterns:
        score, snippet_src = _any_match(p, ["name"], q)
        for fld in ("character_tags", "situation_tags", "typical_behavior",
                    "dialogue_style", "scene_function", "risks",
                    "recommended_plot_followup", "evidence"):
            v = getattr(p, fld, None) or []
            joined = " ".join(str(x) for x in v)
            hit, s = _hit(joined, q)
            if hit:
                score += s // 2  # secondary fields, half weight
                if not snippet_src:
                    snippet_src = joined
        if ql in (p.name or "").lower():
            score += 60
        if score > 0:
            results.append({
                "type": "behavior_pattern",
                "id": p.id,
                "title": p.name,
                "snippet": _snippet(snippet_src, q),
                "link": "/study",
                "score": score,
            })

    # ---- sort + cap ----
    results.sort(key=lambda r: (-r["score"], r["type"], r["id"]))
    return {"ok": True, "data": results[:limit], "q": q, "total": len(results)}
