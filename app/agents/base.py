"""Agent 基类。

对应工程方案：
- 第 12 节 Blind Multi-Agent Architecture
- 第 13 节 Agent 体系
- 第 40 节 agent_runs（每一次 LLM 调用必须可重放）
- 第 43 节 Prompt Constitution

第 12 节硬性约束 —— 禁止 Agent 相互锚定：

    在提交之前：任何专家 Agent 不知道其他 Agent 的结论。

    错误：
        紫微说好 → 八字看到紫微结论 → 八字也说好 → 奇门看到前两者 → 强化

    正确：
        ZiweiAgent ─┐
        BaziAgent  ─┤
        QimenAgent ─┼── FusionAgent
        RealityAgent┤
        NullAgent  ─┘

因此 AgentContext 结构上不提供任何 peer agent 的输出。
第 20.11 节 AgentCollusionAttack 会在事后检测是否发生锚定。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from app.utils import utcnow
from typing import Any

from sqlmodel import Session

from app.config import get_settings
from app.models.registry import AgentRun
from app.providers.base import (
    LLMRequest,
    LLMResponse,
    Tier,
    get_provider,
    new_run_id,
)
from .constitution import PROMPT_CONSTITUTION, ROLE_PROMPTS


@dataclass
class AgentContext:
    """Agent 输入上下文。

    第 12 节：本结构中不存在任何 peer agent 的结论字段。
    若需要多 Agent 协作，只能通过 FusionAgent 消费结构化 Signal，
    而不是让 Agent 之间互看输出。
    """

    user_id: int
    session: Session

    # 目标事件
    target_event: str = ""
    domain: str = ""

    # 输入数据（deterministic 计算结果 / 现实数据）
    payload: dict[str, Any] = field(default_factory=dict)

    # 血缘
    prediction_candidate_id: str | None = None
    prediction_id: str | None = None

    # 实验模式（第 34 节）
    experiment_arm: str | None = None


@dataclass
class AgentResult:
    """Agent 输出。"""

    agent: str
    run_id: str
    ok: bool

    # 结构化输出（进入下游的必须是结构化内容，第 14 节）
    output: dict[str, Any] = field(default_factory=dict)

    # 原始文本（仅审计，不进入 Fusion）
    raw_text: str = ""
    error: str | None = None

    tokens_in: int | None = None
    tokens_out: int | None = None
    duration_ms: int = 0


class BaseAgent(ABC):
    """Agent 抽象基类。

    子类只需实现 build_messages() 与 parse_output()。
    run() 负责：Prompt 宪法注入 → LLM 调用 → agent_runs 落库 → 解析。
    """

    name: str = "BaseAgent"
    tier: Tier = "reasoning"
    prompt_key: str = "base"
    temperature: float | None = None

    # ------------------------------------------------------------------
    def system_prompt(self) -> str:
        """系统 Prompt = 宪法 + 角色指令（第 43 节）。"""
        role = ROLE_PROMPTS.get(self.name, "")
        return f"{PROMPT_CONSTITUTION}\n\n---\n\n# 你的角色\n\n{role}".strip()

    @abstractmethod
    def build_messages(self, ctx: AgentContext) -> list[dict[str, str]]:
        """构造 messages。禁止在此读取其他 Agent 的输出（第 12 节）。"""

    @abstractmethod
    def parse_output(self, response: LLMResponse, ctx: AgentContext) -> dict[str, Any]:
        """解析 LLM 输出为结构化内容。第 14 节：禁止自然语言直接进入下游。"""

    # ------------------------------------------------------------------
    def run(self, ctx: AgentContext) -> AgentResult:
        """执行 Agent，并落库 AgentRun（第 40 节：可重放）。"""
        run_id = new_run_id()
        messages = self.build_messages(ctx)

        provider = get_provider(self.tier)
        # 注意：不使用 response_format=json_object —— 实测 qiyovo 中转站
        # 对该参数会挂起超时。改为 prompt 约束 JSON 输出 + 宽容解析
        # （LLMResponse.json() 容忍 ```json 包裹；parse_output 处理非 JSON）。
        response = provider.complete(
            LLMRequest(
                messages=messages,
                temperature=self.temperature,
            )
        )

        output: dict[str, Any] = {}
        error = response.error
        if response.ok:
            try:
                output = self.parse_output(response, ctx)
            except Exception as exc:  # pragma: no cover
                error = f"{self.name} 输出解析失败：{exc}"

        finished = utcnow()
        run_row = AgentRun(
            run_id=run_id,
            agent=self.name,
            provider=response.provider,
            model=response.model,
            temperature=self.temperature,
            tier=self.tier,
            prompt_version=get_settings().PROMPT_VERSION,
            model_version=get_settings().MODEL_VERSION,
            input_json={"messages": messages, "payload_keys": sorted(ctx.payload)},
            output_json=output,
            started_at=finished,
            finished_at=finished,
            duration_ms=response.duration_ms,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            error=error,
            # 第 12 节：本框架下 Agent 永远看不到其他 Agent 的输出
            saw_other_agents=False,
            prediction_candidate_id=ctx.prediction_candidate_id,
            prediction_id=ctx.prediction_id,
        )
        ctx.session.add(run_row)
        ctx.session.commit()

        return AgentResult(
            agent=self.name,
            run_id=run_id,
            ok=error is None,
            output=output,
            raw_text=response.content,
            error=error,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            duration_ms=response.duration_ms,
        )

    def _user_message(self, text: str) -> dict[str, str]:
        return {"role": "user", "content": text}


class DeterministicAgent(BaseAgent):
    """不调用 LLM 的确定性 Agent 基类。

    第 42 节：Rule Calculation → 程序，无 LLM。
    例如 NullAgent、OutcomeCollectorAgent 的定位匹配部分。
    """

    tier: Tier = "cheap"

    def build_messages(self, ctx: AgentContext) -> list[dict[str, str]]:
        return []

    def parse_output(self, response: LLMResponse, ctx: AgentContext) -> dict[str, Any]:
        return {}

    @abstractmethod
    def compute(self, ctx: AgentContext) -> dict[str, Any]:
        """纯程序计算。"""

    def run(self, ctx: AgentContext) -> AgentResult:
        run_id = new_run_id()
        try:
            output = self.compute(ctx)
            error = None
        except Exception as exc:
            output = {}
            error = f"{self.name} 计算失败：{exc}"

        run_row = AgentRun(
            run_id=run_id,
            agent=self.name,
            provider="deterministic",
            model="none",
            tier="cheap",
            prompt_version=get_settings().PROMPT_VERSION,
            input_json={"payload_keys": sorted(ctx.payload)},
            output_json=output,
            finished_at=utcnow(),
            error=error,
            saw_other_agents=False,
            prediction_candidate_id=ctx.prediction_candidate_id,
            prediction_id=ctx.prediction_id,
        )
        ctx.session.add(run_row)
        ctx.session.commit()

        return AgentResult(
            agent=self.name, run_id=run_id, ok=error is None, output=output, error=error
        )
