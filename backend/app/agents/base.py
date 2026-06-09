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
from app.core.sanitize import sanitize_for_storage
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
    project_genre: str | None = None  # P7: genre for prompt routing
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

        # 2. render the prompt (P7: genre-aware routing)
        rendered = await self.engine.resolve_for_agent(
            ctx.db, self.prompt_key, ctx.project_genre, ctx.inputs,
        )
        if rendered is None:
            # No genre mapping — fall back to hardcoded prompt_key
            rendered = await self.engine.render(ctx.db, self.prompt_key, ctx.inputs)
        rendered_body = sanitize_for_storage(rendered.body)
        step.input_prompt = rendered_body
        step.prompt_template_id = rendered.template_id
        step.prompt_version = rendered.version
        step.provider_name = ""  # filled after the call
        await ctx.db.flush()

        # 3. invoke the LLM
        messages = [LLMMessage(role="user", content=rendered_body)]
        try:
            resolved, result = await self.router.chat(
                ctx.db,
                self.role,
                messages,
                temperature=self.extra_temperature,
                max_tokens=self.extra_max_tokens,
                response_format={"type": "json_object"} if self.uses_json_output else None,
                project_id=ctx.project_id,
                task_id=ctx.task.id,
                chapter_id=ctx.chapter_id,
                step_key=self.step_name,
                agent_step_id=step.id,
                task_type=ctx.task.task_type,
                stream=False,
            )
        except Exception as exc:
            step.status = "failed"
            step.error_message = sanitize_for_storage(str(exc))
            step.finished_at = datetime.utcnow()
            await ctx.db.flush()
            raise

        result_content = sanitize_for_storage(result.content)
        step.raw_output = result_content
        step.model_name = result.model
        step.provider_name = resolved.provider.name
        step.is_mock = (result.model or "").startswith("mock-")
        step.input_tokens = result.input_tokens
        step.output_tokens = result.output_tokens
        step.cost_usd = result.cost_usd
        step.duration_ms = result.duration_ms
        step.finished_at = datetime.utcnow()

        parsed: dict[str, Any] | None = None
        if self.uses_json_output:
            parsed = _safe_json_loads(result_content)
            if parsed is None:
                if self.allow_json_fallback:
                    # P0-4 fix: don't blow up the whole chapter over a
                    # single bad critic report. Synthesise a fallback
                    # that the rewriter / continuity / memory steps
                    # can still consume, and tag it so the UI can show
                    # "degraded" instead of "400 BadRequest".
                    parsed = self._build_json_fallback(result_content)
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
                        f"{self.name} 返回非 JSON: {result_content[:800]}",
                        suggestion="请尝试更换模型或在 prompt 中强调返回 JSON。",
                    )
        else:
            parsed = {"content": result_content}
        parsed = sanitize_for_storage(parsed)
        if step.parsed_output is None:
            step.parsed_output = parsed
        if step.status not in ("failed",):
            step.status = "succeeded"
        await ctx.db.flush()

        # 5. record post-hooks (e.g. memory update) defined by subclasses
        await self.after_run(ctx, parsed, result_content)

        return AgentRunResult(
            step_id=step.id,
            agent_name=self.name,
            parsed=parsed,
            raw=result_content,
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

    # 4) Last-ditch: extract known scalar fields from prose via regex.
    # Some step-3.7-flash outputs look like::
    #     **结论**: 存在 1 处人物状态冲突: 林萧已经筑基...
    #     **建议**: 需要在第三章交代...
    # We pull a few common keys the pipeline actually consumes and
    # synthesise a minimal valid dict. The caller is expected to be
    # an agent with ``allow_json_fallback=True`` (Critic, Continuity,
    # MemoryUpdate, ...) and to handle the ``prose_fallback=True``
    # marker as "the model tried, just not in JSON form".
    prose = _extract_prose_fallback(text)
    if prose is not None:
        return prose
    return None


def _extract_prose_fallback(text: str) -> dict[str, Any] | None:
    """Best-effort field extraction when the model wrote prose instead of JSON.

    Looks for two signals commonly present in the agent prompts we ship:
      - a boolean truth marker (「无冲突」「通过」「存在冲突」「发现问题」)
      - a numeric score (「总分 78」「score: 82」「82 分」)
    Returns a minimally populated dict; otherwise None. The output shape
    intentionally matches the agent's expected schema where possible:
      - Continuity: looks for "conflicts" / "ok"
      - Critic:     looks for "total" / "issues"
      - MemoryUpdate: looks for "character_state_updates"
    The caller will overwrite / merge keys the agent's
    ``_build_json_fallback`` produces, so we keep the dict small.
    """
    if not text or len(text.strip()) < 4:
        return None

    snippet = text[:4000]
    result: dict[str, Any] = {"prose_fallback": True, "raw_preview": text[:1000]}

    # Boolean truth — supports Chinese 玄幻 prompts.
    #
    # Note: bare keywords like "冲突" are too noisy — a sentence like
    # "没有发现明显的时间线冲突" (no conflict found) should NOT count as
    # a conflict. We resolve this by looking for an explicit
    # affirmative pattern ("存在X冲突" / "发现X冲突" / "有矛盾" / "fail")
    # first, and only fall back to bare keyword matching if no
    # negation is present in the surrounding sentence.
    falsy_strong = (
        "存在冲突", "发现冲突", "发现矛盾", "有问题", "存在矛盾",
        "fail", "not ok", "存在问题",
    )
    truthy_strong = (
        "无冲突", "无问题", "无矛盾", "通过检查", "一致性良好",
        "前后一致", "全部通过", "完全正确", "ok", "pass",
    )
    falsy_weak = ("冲突", "矛盾", "硬伤")
    truthy_weak = ("通过", "合格", "正确")

    snippet_low = snippet.lower()
    if any(s in snippet_low or s in snippet for s in falsy_strong):
        result["ok"] = False
        result["_prose_signal"] = "conflict_detected"
    elif any(s in snippet_low or s in snippet for s in truthy_strong):
        result["ok"] = True
        result["_prose_signal"] = "clean"
    else:
        # Fall back to weak keywords, but only when they're NOT inside
        # a negation ("没有冲突", "未发现矛盾"). We do this by checking
        # the 4 chars before each match for common negators.
        import re as _re
        def _is_negated(needle: str) -> bool:
            for m in _re.finditer(needle, snippet):
                pre = snippet[max(0, m.start() - 6):m.start()]
                if any(neg in pre for neg in ("没有", "未发现", "不存在", "无", "没", "未")):
                    return True
            return False
        falsy_match = next((s for s in falsy_weak if s in snippet and not _is_negated(s)), None)
        truthy_match = next((s for s in truthy_weak if s in snippet and not _is_negated(s)), None)
        if falsy_match and not truthy_match:
            result["ok"] = False
            result["_prose_signal"] = f"weak_keyword:{falsy_match}"
        elif truthy_match and not falsy_match:
            result["ok"] = True
            result["_prose_signal"] = f"weak_keyword:{truthy_match}"

    # Numeric score — "总分 78", "score: 82", "82 分", "Total: 78/100"
    m = re.search(r"(?:总分|total|score)\s*[:：=]?\s*(\d{1,3})", snippet, re.IGNORECASE)
    if not m:
        m = re.search(r"(\d{1,3})\s*(?:分|/100|/\\d{2,3})", snippet)
    if m:
        score = max(0, min(100, int(m.group(1))))
        result["total"] = score
        result["_prose_score"] = score

    # Return only if we found at least one signal — otherwise this is
    # just noise and the caller should treat the model as totally
    # unparseable.
    if "ok" in result or "total" in result:
        return result
    return None
