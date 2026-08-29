"""LLM Provider 适配层。

对应工程方案：
- 第 41 节 LLM Provider 架构（API Key 只允许后端保存）
- 第 42 节 模型分层
- 第 79 节 模型版本管理

    LLMProvider
    ├── OpenAICompatibleProvider
    ├── AnthropicProvider        （V2）
    ├── GeminiProvider           （V2）
    └── LocalProvider            （V2）

分层策略（第 42 节）：
    Rule Calculation          → 程序，无 LLM
    Signal Formatting         → cheap
    Specialist Interpretation → reasoning（中高）
    Fusion                    → reasoning（强推理）
    Adversarial Review        → reasoning（独立强推理）
    Outcome Parsing           → cheap
    Monthly Audit             → reasoning（强推理）
"""

from __future__ import annotations

import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from app.config import ProviderSettings, get_settings

Tier = Literal["reasoning", "cheap", "vision"]


@dataclass
class LLMResponse:
    """统一的 LLM 响应。第 40 节要求每次调用可重放。"""

    content: str
    model: str = ""
    provider: str = ""
    tier: Tier = "reasoning"

    tokens_in: int | None = None
    tokens_out: int | None = None
    duration_ms: int = 0

    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def json(self) -> Any:
        """尝试解析为 JSON。失败返回 None（调用方须处理）。"""
        try:
            text = self.content.strip()
            # 容忍 ```json 代码块包裹
            if text.startswith("```"):
                text = text.split("```", 2)[1] if "```" in text[3:] else text
                if text.lower().startswith("json"):
                    text = text[4:]
                text = text.strip().rstrip("`").strip()
            return json.loads(text)
        except (json.JSONDecodeError, IndexError):
            return None


@dataclass
class LLMRequest:
    """统一的 LLM 请求。"""

    messages: list[dict[str, str]] = field(default_factory=list)
    temperature: float | None = None
    max_tokens: int | None = None
    response_format_json: bool = False


class LLMProvider(ABC):
    """Provider 抽象基类。"""

    name: str = "abstract"

    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        """执行一次补全调用。"""


class MockProvider(LLMProvider):
    """无 API Key 时的占位 Provider。

    设计原则：未配置模型时系统必须明确「无法预测」，
    而不是编造结果 —— 这与第 43 节「在无法预测时明确放弃预测」一致。
    """

    name = "mock"

    def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content="ABSTAIN",
            model="mock",
            provider="mock",
            error="未配置 LLM Provider，拒绝生成预测（第 43 节：无法预测时明确放弃）",
        )


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI 兼容端点。覆盖大多数中转站与自建网关。"""

    name = "openai_compatible"

    def __init__(self, settings: ProviderSettings, tier: Tier = "reasoning") -> None:
        self.settings = settings
        self.tier = tier
        self._timeout = 120.0

    @property
    def configured(self) -> bool:
        return self.settings.configured

    def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.configured:
            return LLMResponse(
                content="ABSTAIN",
                provider=self.name,
                tier=self.tier,
                error=f"{self.tier} provider 未配置",
            )

        url = self.settings.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": request.messages,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.response_format_json:
            payload["response_format"] = {"type": "json_object"}

        started = time.time()
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            return LLMResponse(
                content="",
                provider=self.name,
                tier=self.tier,
                duration_ms=int((time.time() - started) * 1000),
                error=f"LLM 调用失败：{exc}",
            )

        duration_ms = int((time.time() - started) * 1000)
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            return LLMResponse(
                content="",
                provider=self.name,
                tier=self.tier,
                duration_ms=duration_ms,
                error=f"LLM 响应格式异常：{exc}",
            )

        usage = data.get("usage") or {}
        return LLMResponse(
            content=content,
            model=str(data.get("model", self.settings.model)),
            provider=self.name,
            tier=self.tier,
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
            duration_ms=duration_ms,
        )


# ----------------------------------------------------------------------
# Provider 工厂（第 42 节分层）
# ----------------------------------------------------------------------
def get_provider(tier: Tier = "reasoning") -> LLMProvider:
    """按分层取得 Provider。未配置则返回 MockProvider。"""
    settings = get_settings()
    ps = settings.provider(tier)
    if not ps.configured:
        return MockProvider()
    return OpenAICompatibleProvider(ps, tier=tier)


def new_run_id() -> str:
    return f"RUN-{uuid.uuid4().hex[:12]}"
