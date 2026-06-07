"""LLM helper for DeepStudy stage executors.

Provides a thin wrapper around LLMRouter + PromptEngine so that each
stage handler can call the LLM without the full BaseAgent /
AgentContext machinery (DeepStudy stages don't have their own
AgentTask row — they run inside a StudyRun).

Usage inside a stage::

    from app.services.deepstudy.stages.llm_helper import call_llm

    resolved, result = await call_llm(
        db=db,
        role="StudyAgent",
        prompt_key="study_character",
        inputs={"chapter_text": text, "existing_characters": "无"},
        response_format={"type": "json_object"},
    )
    parsed = _safe_json_loads(result.content)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm.client import LLMMessage
from app.services.llm.router import LLMRouter
from app.services.prompt_engine import PromptEngine

logger = logging.getLogger(__name__)

# Singleton getters — lazy-initialised on first call.

_router: LLMRouter | None = None
_engine: PromptEngine | None = None


def _get_router() -> LLMRouter:
    global _router
    if _router is None:
        from app.services.llm.router import LLMRouter as R
        from app.services.llm.client import LLMClient
        client = LLMClient()
        _router = R(client)
    return _router


def _get_engine() -> PromptEngine:
    global _engine
    if _engine is None:
        _engine = PromptEngine()
    return _engine


async def call_llm(
    db: AsyncSession,
    *,
    role: str,
    prompt_key: str,
    inputs: dict[str, Any],
    project_genre: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_format: dict[str, str] | None = None,
    project_id: int | None = None,
    task_id: int | None = None,
    chapter_id: int | None = None,
    step_key: str | None = None,
    task_type: str = "deepstudy",
) -> tuple[Any, Any]:
    """Call the LLM with a rendered prompt and return (resolved, result).

    This is a simplified version of BaseAgent.run() that:
    - Renders the prompt via PromptEngine
    - Sends it through LLMRouter.chat() with fallback support
    - Does NOT create AgentStep / AgentTask rows (DeepStudy has its own audit)
    """
    router = _get_router()
    engine = _get_engine()

    # 1. Render the prompt
    rendered = await engine.resolve_for_agent(db, prompt_key, project_genre, inputs)
    if rendered is None:
        rendered = await engine.render(db, prompt_key, inputs)

    # 2. Build messages
    messages = [LLMMessage(role="user", content=rendered.body)]

    # 3. Call LLM
    resolved, result = await router.chat(
        db,
        role,
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
        project_id=project_id,
        task_id=task_id,
        chapter_id=chapter_id,
        step_key=step_key or prompt_key,
        task_type=task_type,
        stream=False,
    )

    return resolved, result


def safe_json_loads(text: str) -> dict[str, Any] | None:
    """Parse JSON from LLM output with multiple fallback strategies.

    Copied from agents/base.py for use without importing the full BaseAgent.
    """
    if not text:
        return None

    # 1) Direct parse
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # 2) Strip ```json ... ``` fences
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            return None

    # 3) Find first balanced { ... }
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        end = -1
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end != -1:
            candidate = text[start : end + 1]
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass
        start = text.find("{", start + 1)

    return None


def truncate_text(text: str, max_chars: int = 6000) -> str:
    """Truncate text to max_chars, adding ellipsis if needed."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...(文本过长已截断)"
