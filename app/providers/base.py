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
        """尝试解析为 JSON。失败返回 None（调用方须处理）。

        容错策略（免费模型池常见非纯 JSON 输出）：
        1. 剥离 ```json 代码块包裹；
        2. 整体解析；
        3. 从文本中提取第一个完整 JSON 对象/数组。
        """
        text = (self.content or "").strip()

        # 1. 剥离代码块包裹
        if text.startswith("```"):
            inner = text.strip("`").strip()
            if inner.lower().startswith("json"):
                inner = inner[4:]
            text = inner.strip()

        # 2. 整体解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 3. 提取第一个完整 JSON 对象 / 数组
        for open_ch, close_ch in (("{", "}"), ("[", "]")):
            start = text.find(open_ch)
            if start == -1:
                continue
            depth = 0
            for i in range(start, len(text)):
                if text[i] == open_ch:
                    depth += 1
                elif text[i] == close_ch:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start : i + 1])
                        except json.JSONDecodeError:
                            break
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
    """OpenAI 兼容端点。覆盖大多数中转站与自建网关。

    健壮性（应对免费模型池的瞬时 5xx）：
        - 5xx / 网络错误自动重试，最多 3 次
        - 4xx（key 错误、余额不足）不重试，直接返回错误
    """

    name = "openai_compatible"

    def __init__(self, settings: ProviderSettings, tier: Tier = "reasoning") -> None:
        self.settings = settings
        self.tier = tier
        # 端点实测 ~5s 响应；30s 足够且不会无限挂起
        self._timeout = 30.0
        self.max_retries = 3

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
            # 显式关闭流式：部分中转站（如 qiyovo）不传 stream 时默认返回
            # SSE 流（data: {...}），导致 resp.json() 解析失败。
            "stream": False,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.response_format_json:
            payload["response_format"] = {"type": "json_object"}

        started = time.time()
        last_error = f"{self.tier} provider 调用失败"

        for attempt in range(self.max_retries):
            try:
                # trust_env=False：禁用系统代理（HTTPS_PROXY 等）。
                # 否则 httpx 走本机代理（如 127.0.0.1:2080），
                # 代理连不上外网端点时请求会挂起到超时。
                with httpx.Client(timeout=self._timeout, trust_env=False) as client:
                    resp = client.post(url, headers=headers, json=payload)

                # 5xx：瞬时故障，重试
                if resp.status_code >= 500:
                    last_error = f"HTTP {resp.status_code}"
                    if attempt < self.max_retries - 1:
                        time.sleep(1 + attempt)
                        continue

                resp.raise_for_status()
                data = resp.json()
                break
            except (httpx.HTTPError, ValueError) as exc:
                last_error = str(exc)
                if attempt < self.max_retries - 1:
                    time.sleep(1 + attempt)
        else:
            return LLMResponse(
                content="",
                provider=self.name,
                tier=self.tier,
                duration_ms=int((time.time() - started) * 1000),
                error=f"LLM 调用失败（重试 {self.max_retries} 次）：{last_error}",
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
