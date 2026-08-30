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

from app.config import ProviderSettings

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

    # 思考链路（reasoning/CoT）。deepseek-v4-flash 等推理模型
    # 会在独立字段返回英文思考过程，正文在 content 里。
    # 保留此字段用于审计与可选展示，绝不当成正文解析。
    reasoning: str = ""

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


def _parse_sse(text: str) -> str:
    """解析 SSE（text/event-stream）响应，累积 content 字段。

    部分中转站（如 qiyovo）即使请求 stream=false 仍返回
    `data: {...chunk...}` 流。逐行解析 data: 载荷，拼出完整内容。
    """
    parts: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        try:
            obj = json.loads(line[5:].strip())
            choices = obj.get("choices") or []
            if choices:
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                if content:
                    parts.append(str(content))
        except (json.JSONDecodeError, IndexError, TypeError):
            continue
    return "".join(parts)


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
        # 端点实测：命理批示等长请求 43~56s；推理模型思考链路长时更久。
        # 180s 给足「思考 + 正文」的生成时间，又不至于无限挂起。
        self._timeout = 180.0
        # 重试 5 次（qiyovo 中转站实测成功率仅约 60%，失败模式有三种：
        # HTTP 500 / HTTP 200 + error 包体 / HTTP 200 + 空 choices。
        # 60% 成功率下 3 次全失败概率 6.4%，5 次降到 1%，必须重试兜底）
        self.max_retries = 5

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
                        time.sleep(1 + attempt * 2)
                        continue

                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if "event-stream" in content_type:
                    # 中转站仍返回 SSE 流：解析 data: 行拼出内容
                    data = {
                        "choices": [{"message": {"content": _parse_sse(resp.text)}}],
                        "usage": {},
                    }
                else:
                    data = resp.json()

                # 软错误兜底：qiyovo 中转站有四种失败模式（HTTP 200 但无效）：
                #   1. {"error": {...}}                     → 有 error 字段
                #   2. {"code":502,"message":"overloaded"}  → 有 code 无 choices
                #   3. choices 为空 / message 缺失          → 无内容
                #   4. content 与 reasoning 均为空          → 空回复
                if isinstance(data, dict):
                    choices = data.get("choices")
                    msg = choices[0].get("message") if isinstance(choices, list) and choices else None
                    content_ok = bool(msg and (msg.get("content") or msg.get("reasoning")))
                    if "error" in data or ("code" in data and "choices" not in data) or not content_ok:
                        err_msg = (
                            data.get("error")
                            or data.get("message")
                            or ("空回复" if not content_ok else None)
                            or str(data)[:120]
                        )
                        last_error = f"upstream soft-error: {err_msg}"
                        if attempt < self.max_retries - 1:
                            time.sleep(1 + attempt * 2)
                            continue
                break
            except (httpx.HTTPError, ValueError) as exc:
                last_error = str(exc)
                if attempt < self.max_retries - 1:
                    time.sleep(1 + attempt * 2)
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
            message = data["choices"][0]["message"] or {}
            content = message.get("content") or ""
            # 思考链路单独提取（deepseek-v4-flash 的 reasoning 字段），
            # 不混入 content，避免污染正文解析。
            reasoning = message.get("reasoning") or ""
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
            reasoning=reasoning,
        )


# ----------------------------------------------------------------------
# Provider 工厂（第 42 节分层）
# ----------------------------------------------------------------------
def get_provider(tier: Tier = "reasoning") -> LLMProvider:
    """按分层取得 Provider。未配置则返回 MockProvider。

    配置来源：运行时覆盖层（设置页保存）> .env（第 41 节）。
    """
    from app.services.llm_config import effective_provider

    ps = effective_provider(tier)
    if not ps.configured:
        return MockProvider()
    return OpenAICompatibleProvider(ps, tier=tier)


def new_run_id() -> str:
    return f"RUN-{uuid.uuid4().hex[:12]}"
