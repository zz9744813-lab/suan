"""DetailGuard: enforce hard rules and surface conflicts after a draft.

Spec §9.2. The pre-write checklist is built from memory states; the post-write
check is a deterministic pass over the draft text using keyword cues.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.services.context_compiler import ChapterContext


@dataclass
class DetailCheckResult:
    hard_conflicts: list[str] = field(default_factory=list)
    soft_warnings: list[str] = field(default_factory=list)
    foreshadow_misses: list[str] = field(default_factory=list)


class DetailGuard:
    def pre_write_checklist(self, ctx: ChapterContext) -> list[str]:
        return list(ctx.detail_guard_reminders)

    def post_write_check(self, ctx: ChapterContext, draft: str) -> DetailCheckResult:
        result = DetailCheckResult()
        text = draft or ""

        # injury conflict
        for st in ctx.character_states:
            injury = (st.get("injury_state") or "").strip()
            if not injury:
                continue
            name = st["name"]
            # crude: if injury mentions an arm and the text says "双手剑" with that name nearby
            if "左臂" in injury and "双手剑" in text:
                result.hard_conflicts.append(
                    f"{name} 当前左臂受伤（{injury}），但正文出现「双手剑」。"
                )
            if "受伤" in injury and "康复" in text and _within_window(text, "康复", name, window=80):
                result.soft_warnings.append(
                    f"{name} 伤势标记为 {injury}，正文却出现康复描述。请确认是否本章已恢复。"
                )

        # secret conflict
        for st in ctx.character_states:
            name = st["name"]
            for secret in st.get("secrets") or []:
                # if draft explicitly reveals the secret with the name, raise hard
                if _reveals(text, name, secret):
                    result.hard_conflicts.append(
                        f"{name} 的秘密「{secret}」不应在本章被他人知道，请检查。"
                    )

        # foreshadow advance requirement
        for f in ctx.active_foreshadows:
            exp = f.get("expected_payoff_chapter")
            if exp is None:
                continue
            if abs(exp - ctx.chapter_no) <= 1:
                if f["name"] not in text and f.get("related_items"):
                    if not any(item in text for item in f["related_items"]):
                        result.foreshadow_misses.append(
                            f"伏笔「{f['name']}」计划在第 {exp} 章推进，但正文未出现相关物品/人物。"
                        )

        # continuity: prior chapter ending should be honored
        prior = ctx.prior_chapter
        if prior and prior.get("summary"):
            if "追杀" in (prior.get("summary") or "") and "追杀" not in text and "追" not in text:
                result.soft_warnings.append(
                    f"上一章结尾包含追杀压力，本章开头似乎未承接。"
                )

        return result


def _within_window(text: str, needle: str, name: str, window: int) -> bool:
    idx = text.find(needle)
    if idx == -1:
        return False
    start = max(0, idx - window)
    end = min(len(text), idx + window)
    return name in text[start:end]


def _reveals(text: str, name: str, secret: str) -> bool:
    # very simple: if both name and a salient token of the secret appear in the
    # same sentence, treat as a likely reveal
    sentences = re.split(r"[。！？\n]", text)
    for s in sentences:
        if name in s:
            tokens = re.findall(r"[\u4e00-\u9fff]{3,}", secret)
            if any(tok in s for tok in tokens[:3]):
                return True
    return False


_detail_guard_singleton: DetailGuard | None = None


def get_detail_guard() -> DetailGuard:
    global _detail_guard_singleton
    if _detail_guard_singleton is None:
        _detail_guard_singleton = DetailGuard()
    return _detail_guard_singleton
