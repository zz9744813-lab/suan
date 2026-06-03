"""Prompt engine: load templates/versions and render with strict isolation.

The engine enforces the spec §7 isolation rules by refusing to allow
`forbidden_inputs` to leak into the rendered prompt, and by stamping a
provenance block listing exactly which template/version was used.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import bad_request, not_found
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
    warnings: list[str]


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
            warnings=warnings,
        )


_engine_singleton: PromptEngine | None = None


def get_prompt_engine() -> PromptEngine:
    global _engine_singleton
    if _engine_singleton is None:
        _engine_singleton = PromptEngine()
    return _engine_singleton
