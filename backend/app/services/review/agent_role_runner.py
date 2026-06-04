"""AgentRoleRunner: 按 AgentRole.key 运行模型 (P6 §4.1).

设计要点 (跟旧 ``LLMRouter`` 严格区分):

1. **不复用旧 router**: 旧 router 只认 ``ModelRoleAssignment.role``
   字符串 (Chief / Draft / Reader 这种粗粒度), 5 个 reader 需要独立
   provider / model / prompt 绑定, 所以这里从 ``AgentModelBinding`` 直接
   走 ``LLMClient.chat``, 绕开 ``LLMRouter.resolve``。

2. **agent_key 一一对应 PromptTemplate.template_key**: reader_hook →
   reader_hook_comment, chief_comment_moderator → chief_comment_triage
   (用 task_prompt 那种). 我们用 ``agent_key`` 当 template_key 的回退值,
   调用方可以显式 override。

3. **AgentRun 是真相**: 每次调用都写一行 ``AgentRun``, 字段按 spec §8.4
   填齐 (provider_id / model_name / tokens / cost / elapsed_ms / status
   / output_summary), 便于 P4 §15 "状态从 AgentStep 真实数据派生"。

4. **解析失败不抛, 但标记**: 顶层 LLMError 子类 (auth / connection /
   rate_limit) 抛给上层; 但 JSON 解析失败把原始 content 装到
   ``parsed['_raw']``, run.status = 'failed' 留痕。reader/chief 的下游
   service (ReaderReviewService / CommentTriageService) 必须自己判断
   parsed 是否可用。

P2 验收用例: ``POST /api/reviews/runs`` 触发的 reader_review 任务
跑完必须生成 5 条 ``author_type='reader_agent'`` 的 ReviewComment。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import bad_request
from app.models.agent_role import (
    AgentModelBinding,
    AgentPromptBinding,
    AgentRole,
    AgentRun,
    AgentRunEvent,
)
from app.models.model_provider import ModelProvider
from app.services.llm.client import (
    LLMAuthError,
    LLMClient,
    LLMConnectionError,
    LLMError,
    LLMMessage,
    LLMRequest,
    LLMRateLimitError,
    get_llm_client,
)
from app.services.prompt_engine import PromptEngine, get_prompt_engine


@dataclass
class AgentRoleRunResult:
    """一次 AgentRoleRunner.run 的成功结果 (含 parse 失败)."""

    parsed: dict[str, Any]
    raw_content: str
    run_id: int
    model: str
    provider_name: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: int
    template_key: str
    template_version: int
    parse_error: str | None = None  # JSON 解析失败时记录

    @property
    def ok(self) -> bool:
        return self.parse_error is None


class AgentRoleRunner:
    def __init__(
        self,
        *,
        client: LLMClient | None = None,
        engine: PromptEngine | None = None,
    ) -> None:
        self.client = client or get_llm_client()
        self.engine = engine or get_prompt_engine()

    async def run(
        self,
        db: AsyncSession,
        *,
        agent_key: str,
        project_id: int | None = None,
        task_id: int | None = None,
        run_type: str = "agent_role",
        inputs: dict[str, Any] | None = None,
        # 显式 override: 默认按 agent_key 查 template
        template_key: str | None = None,
        # "json_object" 走 strict, "text" 走 prose, None 走 LLM 默认
        response_format: str | None = "json_object",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AgentRoleRunResult:
        inputs = inputs or {}

        # 1. AgentRole
        role = (
            await db.execute(
                select(AgentRole).where(AgentRole.key == agent_key)
            )
        ).scalar_one_or_none()
        if role is None:
            raise bad_request(
                f"AgentRole '{agent_key}' 不存在",
                suggestion="检查 seed 是否成功, 或在「模型配置」页创建该角色",
            )
        if not role.enabled:
            raise bad_request(
                f"AgentRole '{agent_key}' (id={role.id}) 已禁用, 不能运行",
            )

        # 2. AgentModelBinding
        binding = (
            await db.execute(
                select(AgentModelBinding).where(
                    AgentModelBinding.agent_role_id == role.id,
                )
            )
        ).scalar_one_or_none()
        if binding is None or binding.provider_id is None or not binding.model_name:
            raise bad_request(
                f"角色 '{role.display_name}' 未绑定模型",
                suggestion=(
                    "请在「模型配置」页为该角色绑定一个 Provider + model, "
                    "或运行 `python -m app.seed` 重建默认 binding"
                ),
            )

        # 3. Provider
        provider = await db.get(ModelProvider, binding.provider_id)
        if provider is None:
            raise bad_request(
                f"角色 '{role.display_name}' 绑定的 Provider id={binding.provider_id} 不存在",
            )
        if not provider.enabled:
            raise bad_request(
                f"角色 '{role.display_name}' 绑定的 Provider '{provider.name}' 已禁用",
            )

        # 4. AgentPromptBinding (仅作为参考, 真实 template_key 走参数)
        #    现阶段所有 reader / chief 的 agent_key 跟 template_key 一一对应,
        #    暂不强制使用 binding.task_prompt_template_id, 留待 P4 升级。
        _ = (
            await db.execute(
                select(AgentPromptBinding).where(
                    AgentPromptBinding.agent_role_id == role.id,
                )
            )
        ).scalar_one_or_none()

        # 5. Render prompt
        effective_template_key = template_key or agent_key
        rendered = await self.engine.render(db, effective_template_key, inputs)

        # 6. AgentRun (status=running)
        run = AgentRun(
            agent_role_id=role.id,
            project_id=project_id,
            task_id=task_id,
            run_type=run_type,
            status="running",
            provider_id=provider.id,
            model_name=binding.model_name,
            started_at=datetime.utcnow(),
            input_summary=json.dumps(
                {k: type(v).__name__ for k, v in inputs.items()},
                ensure_ascii=False,
            )[:500],
        )
        db.add(run)
        await db.flush()
        run_id = run.id

        db.add(AgentRunEvent(
            agent_run_id=run_id,
            event_type="started",
            message=f"running {agent_key} via {provider.name}/{binding.model_name}",
            payload={
                "template_key": effective_template_key,
                "template_version": rendered.version,
                "input_count": len(inputs),
            },
        ))

        # 7. Build LLM request
        temperature_eff = (
            temperature if temperature is not None
            else (binding.temperature if binding.temperature is not None else 0.7)
        )
        max_tokens_eff = (
            max_tokens if max_tokens is not None
            else (binding.max_tokens if binding.max_tokens is not None else 1600)
        )
        request = LLMRequest(
            model=binding.model_name,
            messages=[LLMMessage(role="user", content=rendered.body)],
            temperature=temperature_eff,
            max_tokens=max_tokens_eff,
            response_format=(
                {"type": response_format} if response_format in ("json_object", "text")
                else None
            ),
            extra=binding.extra_body or {},
        )

        # 8. Call LLM
        t0 = time.perf_counter()
        try:
            result = await self.client.chat(
                base_url=provider.base_url,
                api_key=provider.api_key,
                request=request,
                provider_extra=provider.extra or {},
            )
        except (LLMAuthError, LLMConnectionError, LLMRateLimitError) as exc:
            err = f"{type(exc).__name__}: {exc}"
            run.status = "failed"
            run.error_message = err
            run.finished_at = datetime.utcnow()
            run.elapsed_ms = int((time.perf_counter() - t0) * 1000)
            db.add(AgentRunEvent(
                agent_run_id=run_id,
                event_type="failed",
                message=err,
                payload=None,
            ))
            await db.flush()
            raise
        # 其他 LLMError: 也标 failed, 但重新 raise
        except LLMError as exc:
            err = f"{type(exc).__name__}: {exc}"
            run.status = "failed"
            run.error_message = err
            run.finished_at = datetime.utcnow()
            run.elapsed_ms = int((time.perf_counter() - t0) * 1000)
            db.add(AgentRunEvent(
                agent_run_id=run_id,
                event_type="failed",
                message=err,
                payload=None,
            ))
            await db.flush()
            raise

        duration_ms = int((time.perf_counter() - t0) * 1000)

        # 9. Parse JSON
        parsed: dict[str, Any]
        parse_error: str | None = None
        text = (result.content or "").strip()
        if not text:
            parsed = {"_raw": ""}
            parse_error = "LLM returned empty content"
        else:
            try:
                obj = json.loads(text)
                if isinstance(obj, dict):
                    parsed = obj
                elif isinstance(obj, list):
                    # 容忍 list 顶层 — 包成 comments / items 字段
                    parsed = {"_items": obj}
                else:
                    parsed = {"_value": obj}
            except json.JSONDecodeError as exc:
                # 不抛, 把原文装进来, 让下游判断
                parsed = {"_raw": text[:2000]}
                parse_error = f"JSONDecodeError: {exc}"

        # 10. Update run
        run.status = "succeeded" if parse_error is None else "failed"
        run.error_message = parse_error
        run.finished_at = datetime.utcnow()
        run.elapsed_ms = duration_ms
        run.input_tokens = result.input_tokens
        run.output_tokens = result.output_tokens
        run.cost_usd = result.cost_usd
        if parse_error:
            run.output_summary = (
                f"PARSE_ERROR ({parse_error[:80]}); "
                f"raw[:200]={text[:200]!r}"
            )
        else:
            # 截短 summary — 完整 raw 在 AgentRunEvent payload 里
            run.output_summary = json.dumps(parsed, ensure_ascii=False)[:500]

        # 11. Event
        db.add(AgentRunEvent(
            agent_run_id=run_id,
            event_type="succeeded" if parse_error is None else "failed",
            message=(
                f"OK in {duration_ms}ms, "
                f"{result.input_tokens}+{result.output_tokens} tokens, "
                f"${result.cost_usd:.4f}"
                if parse_error is None
                else f"parse error: {parse_error}"
            ),
            payload={
                "template_key": effective_template_key,
                "template_version": rendered.version,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost_usd": result.cost_usd,
                "duration_ms": duration_ms,
            },
        ))
        await db.flush()

        return AgentRoleRunResult(
            parsed=parsed,
            raw_content=result.content,
            run_id=run_id,
            model=binding.model_name,
            provider_name=provider.name,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_usd=result.cost_usd,
            duration_ms=duration_ms,
            template_key=effective_template_key,
            template_version=rendered.version,
            parse_error=parse_error,
        )


_runner_singleton: AgentRoleRunner | None = None


def get_agent_role_runner() -> AgentRoleRunner:
    global _runner_singleton
    if _runner_singleton is None:
        _runner_singleton = AgentRoleRunner()
    return _runner_singleton
