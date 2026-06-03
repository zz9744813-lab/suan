"""Base class shared by all agents.

Each agent owns a name, a role for the LLM router, a prompt template key, and
a `run` method. The pipeline instantiates a fresh agent per call but the
prompt engine / LLM router are shared singletons.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import bad_request
from app.models.task import AgentStep, AgentTask
from app.services.llm.client import LLMMessage
from app.services.llm.router import LLMRouter, ResolvedCall
from app.services.prompt_engine import PromptEngine, RenderedPrompt


@dataclass
class AgentContext:
    """Per-run inputs collected by the pipeline."""
    db: AsyncSession
    task: AgentTask
    project_id: int
    chapter_id: int | None
    inputs: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRunResult:
    step_id: int
    agent_name: str
    parsed: dict[str, Any] | None
    raw: str
    resolved: ResolvedCall
    duration_ms: int
    cost_usd: float
    input_tokens: int
    output_tokens: int


class BaseAgent(ABC):
    name: str = "BaseAgent"
    role: str = "Default"  # for LLM router
    prompt_key: str = ""
    step_name: str = "run"
    uses_json_output: bool = True
    # P0-4 fix: by default, an agent whose model returns non-JSON (when
    # ``uses_json_output=True``) is considered a hard failure and the
    # whole pipeline is aborted. For Critic-like agents this is too
    # strict — a missing or unparseable critic report is not a reason
    # to lose the chapter. Subclasses that want graceful degradation
    # (currently only ``CriticAgent``) flip this to True; the run-loop
    # then synthesises a fallback parsed output tagged with
    # ``parse_failed: true`` so the UI can surface it as
    # "degraded" rather than a hard 400.
    allow_json_fallback: bool = False
    extra_temperature: float | None = None
    extra_max_tokens: int | None = None

    def __init__(self, router: LLMRouter, engine: PromptEngine) -> None:
        self.router = router
        self.engine = engine

    async def run(self, ctx: AgentContext) -> AgentRunResult:
        # 1. record the step row up front
        step = AgentStep(
            task_id=ctx.task.id,
            project_id=ctx.project_id,
            chapter_id=ctx.chapter_id,
            agent_name=self.name,
            step_name=self.step_name,
            status="running",
            started_at=datetime.utcnow(),
        )
        ctx.db.add(step)
        await ctx.db.flush()

        # 2. render the prompt
        rendered = await self.engine.render(ctx.db, self.prompt_key, ctx.inputs)
        step.input_prompt = rendered.body
        step.prompt_template_id = rendered.template_id
        step.prompt_version = rendered.version
        step.provider_name = ""  # filled after the call
        await ctx.db.flush()

        # 3. invoke the LLM
        messages = [LLMMessage(role="user", content=rendered.body)]
        try:
            resolved, result = await self.router.chat(
                ctx.db,
                self.role,
                messages,
                temperature=self.extra_temperature,
                max_tokens=self.extra_max_tokens,
                response_format={"type": "json_object"} if self.uses_json_output else None,
            )
        except Exception as exc:
            step.status = "failed"
            step.error_message = str(exc)
            step.finished_at = datetime.utcnow()
            await ctx.db.flush()
            raise

        # 4. persist step result
        step.raw_output = result.content
        step.model_name = result.model
        step.provider_name = resolved.provider.name
        step.input_tokens = result.input_tokens
        step.output_tokens = result.output_tokens
        step.cost_usd = result.cost_usd
        step.duration_ms = result.duration_ms
        step.finished_at = datetime.utcnow()

        parsed: dict[str, Any] | None = None
        if self.uses_json_output:
            parsed = _safe_json_loads(result.content)
            if parsed is None:
                if self.allow_json_fallback:
                    # P0-4 fix: don't blow up the whole chapter over a
                    # single bad critic report. Synthesise a fallback
                    # that the rewriter / continuity / memory steps
                    # can still consume, and tag it so the UI can show
                    # "degraded" instead of "400 BadRequest".
                    parsed = self._build_json_fallback(result.content)
                    step.parsed_output = parsed
                    step.error_message = (
                        "模型返回内容无法解析为 JSON，已使用 fallback 评分"
                    )
                    step.status = "succeeded"
                else:
                    step.status = "failed"
                    step.error_message = "模型返回内容无法解析为 JSON"
                    await ctx.db.flush()
                    raise bad_request(
                        f"{self.name} 返回非 JSON: {result.content[:800]}",
                        suggestion="请尝试更换模型或在 prompt 中强调返回 JSON。",
                    )
        else:
            parsed = {"content": result.content}
        if step.parsed_output is None:
            step.parsed_output = parsed
        if step.status not in ("failed",):
            step.status = "succeeded"
        await ctx.db.flush()

        # 5. record post-hooks (e.g. memory update) defined by subclasses
        await self.after_run(ctx, parsed, result.content)

        return AgentRunResult(
            step_id=step.id,
            agent_name=self.name,
            parsed=parsed,
            raw=result.content,
            resolved=resolved,
            duration_ms=result.duration_ms,
            cost_usd=result.cost_usd,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )

    async def after_run(
        self, ctx: AgentContext, parsed: dict[str, Any] | None, raw: str
    ) -> None:
        """Hook for subclasses. Default does nothing."""

    def _build_json_fallback(self, raw: str) -> dict[str, Any]:
        """Synthesise a parsed dict when the model returned non-JSON.

        Only called when ``allow_json_fallback=True``. The default
        returns a generic envelope; agents whose downstream consumers
        expect a specific shape (Critic → rewriter, etc.) override
        this to produce a minimally useful report instead of a hard
        failure.
        """
        return {
            "parse_failed": True,
            "fallback": True,
            "raw_preview": (raw or "")[:1000],
            "summary": "模型未返回合法 JSON，已使用 fallback。",
        }


def _safe_json_loads(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    # 1) direct parse
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # 2) strip ```json ... ``` fences
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            return None
    # 3) find first balanced { ... } block by tracking nesting depth.
    # Reasoning models (step-3.7-flash, deepseek-r1, o1, ...) often emit
    # Chinese prose *before* the JSON object. The greedy first-{ to last-}
    # can over-match (grab trailing prose after the real JSON ends), so
    # we walk the string and find the *first* complete top-level object.
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
        # move to next { after the failed one
        start = text.find("{", start + 1)
    return None
