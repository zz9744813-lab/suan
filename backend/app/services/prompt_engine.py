"""Prompt engine: load templates/versions and render with strict isolation.

The engine enforces the spec §7 isolation rules by refusing to allow
`forbidden_inputs` to leak into the rendered prompt, and by stamping a
provenance block listing exactly which template/version was used.

P7: Added `resolve_for_agent()` — genre-aware template routing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import bad_request, not_found
from app.models.genre_prompt_map import GenrePromptMapping
from app.models.prompt import PromptTemplate, PromptVersion


_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_\.\-]+)\s*\}\}")


@dataclass
class RenderedPrompt:
    template_id: int
    template_key: str
    version: int
    body: str
    role: str
    category: str
    genre: str | None = None
    warnings: list[str] | None = None


class PromptEngine:
    """Loads active versions and renders with placeholder substitution."""

    async def get_active(self, db: AsyncSession, template_key: str) -> tuple[PromptTemplate, PromptVersion]:
        tpl = (
            await db.execute(
                select(PromptTemplate).where(PromptTemplate.template_key == template_key)
            )
        ).scalar_one_or_none()
        if tpl is None:
            raise not_found("PromptTemplate", template_key)
        # find the active version
        ver = (
            await db.execute(
                select(PromptVersion)
                .where(PromptVersion.template_id == tpl.id, PromptVersion.status == "active")
                .order_by(PromptVersion.version.desc())
            )
        ).scalar_one_or_none()
        if ver is None:
            # fall back to highest version regardless of status
            ver = (
                await db.execute(
                    select(PromptVersion)
                    .where(PromptVersion.template_id == tpl.id)
                    .order_by(PromptVersion.version.desc())
                )
            ).scalar_one_or_none()
        if ver is None:
            raise bad_request(f"Prompt '{template_key}' 没有任何版本。")
        return tpl, ver

    # ============================================================
    # P7: Genre-aware prompt resolution
    # ============================================================
    async def resolve_for_agent(
        self,
        db: AsyncSession,
        agent_role_key: str,
        project_genre: str | None,
        inputs: dict[str, Any],
    ) -> RenderedPrompt:
        """Resolve the best prompt template for (agent, genre) and render it.

        Lookup order:
        1. genre_prompt_mapping WHERE agent_role_key=X AND genre=Y (exact match)
        2. genre_prompt_mapping WHERE agent_role_key=X AND genre="" (generic fallback)
        3. Fall back to the agent's hardcoded prompt_key (legacy path)
        """
        tpl: PromptTemplate | None = None

        # Step 1: exact genre match
        if project_genre:
            mapping = (await db.execute(
                select(GenrePromptMapping)
                .where(
                    GenrePromptMapping.agent_role_key == agent_role_key,
                    GenrePromptMapping.genre == project_genre,
                )
                .order_by(GenrePromptMapping.priority.desc())
                .limit(1)
            )).scalar_one_or_none()
            if mapping:
                tpl = await db.get(PromptTemplate, mapping.prompt_template_id)

        # Step 2: generic fallback (genre="")
        if tpl is None:
            mapping = (await db.execute(
                select(GenrePromptMapping)
                .where(
                    GenrePromptMapping.agent_role_key == agent_role_key,
                    GenrePromptMapping.genre == "",
                )
                .order_by(GenrePromptMapping.priority.desc())
                .limit(1)
            )).scalar_one_or_none()
            if mapping:
                tpl = await db.get(PromptTemplate, mapping.prompt_template_id)

        # Step 3: no mapping found — trigger PromptAutoBinder to create one,
        # then retry. If binder fails or finds no template, return None (caller
        # falls back to hardcoded legacy prompt).
        if tpl is None:
            try:
                from app.services.prompt_auto_binder import get_prompt_auto_binder
                import logging
                _logger = logging.getLogger(__name__)
                genre_for_binder = project_genre or ""
                binder_result = await get_prompt_auto_binder().auto_fill_for_agent_genre(
                    db, agent_role_key, genre_for_binder,
                )
                if binder_result.get("action") in ("created", "updated"):
                    # 绑定成功, 重新查找
                    new_tpl_id = binder_result.get("selected_template_id")
                    if new_tpl_id:
                        tpl = await db.get(PromptTemplate, new_tpl_id)
                        _logger.info(
                            "PromptAutoBinder auto-bound template %s for (%s, %s)",
                            binder_result.get("selected_template_key"),
                            agent_role_key, genre_for_binder,
                        )
            except Exception as _binder_exc:
                import logging
                logging.getLogger(__name__).warning(
                    "PromptAutoBinder failed for (%s, %s): %s",
                    agent_role_key, project_genre, _binder_exc,
                )

        if tpl is None:
            return None  # type: ignore[return-value]

        # Get active version
        ver = (await db.execute(
            select(PromptVersion)
            .where(PromptVersion.template_id == tpl.id, PromptVersion.status == "active")
            .order_by(PromptVersion.version.desc())
        )).scalar_one_or_none()
        if ver is None:
            ver = (await db.execute(
                select(PromptVersion)
                .where(PromptVersion.template_id == tpl.id)
                .order_by(PromptVersion.version.desc())
            )).scalar_one_or_none()
        if ver is None:
            raise bad_request(f"Genre-mapped prompt '{tpl.template_key}' 没有任何版本。")

        return self._render(tpl, ver, inputs)

    async def render(
        self,
        db: AsyncSession,
        template_key: str,
        inputs: dict[str, Any],
    ) -> RenderedPrompt:
        tpl, ver = await self.get_active(db, template_key)
        return self._render(tpl, ver, inputs)

    def render_sync(
        self,
        tpl: PromptTemplate,
        ver: PromptVersion,
        inputs: dict[str, Any],
    ) -> RenderedPrompt:
        return self._render(tpl, ver, inputs)

    def _render(
        self,
        tpl: PromptTemplate,
        ver: PromptVersion,
        inputs: dict[str, Any],
    ) -> RenderedPrompt:
        warnings: list[str] = []
        # spec §7.3 isolation: never let forbidden inputs into the body
        forbidden = set(tpl.forbidden_inputs or [])
        cleaned: dict[str, Any] = {}
        for k, v in inputs.items():
            if k in forbidden:
                warnings.append(f"forbidden input '{k}' was filtered out")
                continue
            cleaned[k] = v

        body = ver.body

        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            if key in cleaned:
                value = cleaned[key]
                if isinstance(value, (list, dict)):
                    import json
                    value = json.dumps(value, ensure_ascii=False, indent=2)
                return str(value)
            return ""

        rendered = _PLACEHOLDER.sub(repl, body)
        return RenderedPrompt(
            template_id=tpl.id,
            template_key=tpl.template_key,
            version=ver.version,
            body=rendered,
            role=tpl.role,
            category=tpl.category,
            genre=tpl.genre,
            warnings=warnings,
        )


_engine_singleton: PromptEngine | None = None


def get_prompt_engine() -> PromptEngine:
    global _engine_singleton
    if _engine_singleton is None:
        _engine_singleton = PromptEngine()
    return _engine_singleton
