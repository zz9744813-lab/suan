"""OpenAI-Compatible chat completions client (spec §1.3).

Works with any provider that exposes `POST {base_url}/chat/completions` and
optionally `GET {base_url}/models` (OpenAI, OpenRouter, DeepSeek, Claude and
Gemini proxies, vLLM, Ollama, etc.).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.services.llm.pricing import estimate_cost_usd

logger = logging.getLogger(__name__)


def _fmt_exc(exc: BaseException) -> str:
    """Render an exception in a way that *always* tells us what it was.

    ``str(httpx.HTTPError)`` is sometimes empty (e.g. ReadTimeout with no
    message). Logging the type name + ``repr`` guarantees we see *something*
    in worker logs when diagnosing a failed call.
    """
    return f"{type(exc).__name__}: {exc!r}"


def _find_last_json_object(text: str) -> str | None:
    """Return the last balanced top-level JSON object/array in ``text``.

    Reasoning models like step-3.7-flash put a long planning monologue
    *before* the actual JSON answer, all inside ``reasoning_content``.
    A naive ``text.find("{")`` to ``text.rfind("}")`` slice often
    over-matches (e.g. swallows the prose after the closing ``}``). We
    walk the string from the end, tracking depth and string state, so we
    get exactly the last balanced ``{...}`` or ``[...]`` block. Returns
    ``None`` if no such block parses.
    """
    if not text:
        return None
    # Prefer the type whose last opener is the most recent. We look for
    # both '}' and ']' at the end and pick whichever is later.
    end = max(text.rfind("}"), text.rfind("]"))
    if end == -1:
        return None
    openers = {"}": "{", "]": "["}
    closer = text[end]
    opener = openers[closer]
    depth = 0
    in_str = False
    escape = False
    for i in range(end, -1, -1):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == closer:
            depth += 1
        elif ch == opener:
            depth -= 1
            if depth == 0:
                candidate = text[i : end + 1]
                try:
                    json.loads(candidate)
                except json.JSONDecodeError:
                    return None
                return candidate
    return None


# R15 / picker-fix-1: markers that often mark the transition from
# the model's *planning prose* to its *actual answer prose* inside
# a single ``reasoning_content`` blob. Tier 1 is "strong" — the model
# uses these when it consciously switches from thinking to writing.
# Tier 2 is "weak" — these appear in the middle of planning too
# (e.g. "好的, 那我就...") so we only trust them when the candidate
# is long enough that the planning is clearly over.
_ANSWER_MARKERS_TIER1 = (
    "以下是正文", "正文如下", "以下是答案", "答案如下",
    "答复如下", "答复：", "答复:", "答案：", "答案:",
    "现在写：", "现在写:", "正式内容：", "正式内容:",
    "输出如下", "输出：", "输出:",
    "---正文---", "---正文---", "--- 答案 ---",
)
_ANSWER_MARKERS_TIER2 = (
    "好的，", "好的:", "好的：", "好，", "好:", "好：",
)


# R15 / picker-stub detection: small JSON objects whose "content" field
# is short placeholder text are usually *envelope stubs* emitted by
# reasoning models at the very end of the planning stream — the real
# answer is the prose BEFORE the stub, not the stub itself. We mark
# such candidates so the picker can skip them.
_STUB_CONTENT_HINTS = (
    "这里放内容", "正文", "TBD", "TODO", "待填", "占位",
    "...", "（", "(", "略", "见下",
)


def _looks_like_json_stub(text: str) -> bool:
    """True if ``text`` parses as a tiny JSON dict whose ``content``
    field is a placeholder string — i.e. the model emitted an empty
    envelope instead of an actual answer.

    Used by the picker to deprioritise such candidates in favour of
    the prose extraction path (strategy 2). False positives are safe:
    the picker just falls through to strategy 2 / 3 / 4.
    """
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return False
    if not isinstance(obj, dict):
        return False
    # Only call it a stub if BOTH (a) the whole object is tiny AND
    # (b) its "content" field is short + contains a placeholder hint.
    if len(text) > 80:
        return False
    content = obj.get("content")
    if not isinstance(content, str):
        return False
    if len(content) > 40:
        return False
    return any(hint in content for hint in _STUB_CONTENT_HINTS)


def _extract_answer_from_prose(text: str) -> str | None:
    """When ``text`` is a mix of planning + answer prose, return the
    *answer portion only*.

    Used by the picker when ``content`` is empty and ``reasoning_content``
    is a single prose blob. Reasoning models like step-3.7-flash on the
    whitedream provider routinely emit ALL their output in
    ``reasoning_content`` — a planning preamble like "用户现在需要我写..."
    followed by the actual chapter / JSON answer. Without this trim the
    picker would return the planning prose and the downstream agent
    would treat the model's own thinking as the user's deliverable.

    Strategy (returns ``None`` if it cannot find a reasonable cut):

      1. Tier-1 markers (strong): find the last occurrence; if found,
         return everything after it (stripped).
      2. Tier-2 markers (weak): only trust them if the text is
         ``>= 1500`` chars (otherwise "好，" might be a one-shot
         agreement, not a switch).
      3. No marker: return the LAST 60 % of the text, assuming the
         answer is at the tail of the model's output stream.

    Returns ``None`` if ``text`` is too short to bother with the
    trim (< 200 chars).
    """
    if not text or len(text) < 200:
        return None
    # Tier 1 — strong markers
    last_t1 = -1
    for m in _ANSWER_MARKERS_TIER1:
        idx = text.rfind(m)
        if idx > last_t1:
            last_t1 = idx
    if last_t1 >= 0:
        cut = text[last_t1:]
        # skip past the marker itself to drop "以下是正文：" / "好的，"
        for m in _ANSWER_MARKERS_TIER1:
            if cut.startswith(m):
                cut = cut[len(m):]
                break
        return cut.lstrip("：:，, \n\t\r")
    # Tier 2 — weak markers, only on long-enough text
    if len(text) >= 1500:
        last_t2 = -1
        for m in _ANSWER_MARKERS_TIER2:
            idx = text.rfind(m)
            if idx > last_t2:
                last_t2 = idx
        if last_t2 >= 0:
            cut = text[last_t2:]
            for m in _ANSWER_MARKERS_TIER2:
                if cut.startswith(m):
                    cut = cut[len(m):]
                    break
            return cut.lstrip("：:，, \n\t\r")
    # Tier 3 — assume the answer lives in the last 60 % of the text
    cut_start = int(len(text) * 0.4)
    # snap to the next newline so we don't start mid-sentence
    nl = text.find("\n", cut_start)
    if 0 < nl - cut_start < 200:
        cut_start = nl + 1
    return text[cut_start:]


# P0-MODEL-11: heuristic detector for "reasoning" / "thinking" model
# variants. Used by ``_do_chat`` to auto-inject
# ``extra_body.reasoning_effort="low"`` so a non-streaming chat call
# doesn't burn its whole ``max_tokens`` budget on internal planning.
#
# This is intentionally conservative — we only match on substrings
# the model name (or the base URL) is unlikely to contain by
# accident. False positives are still safe (we only *add* an
# ``extra_body`` field; we never strip one), but we'd rather be
# too narrow than too wide.
_REASONING_MODEL_HINTS = (
    # StepFun's reasoning flagship + cheap flash variant
    "step-3", "step-r", "stepfun",
    # OpenAI o-series
    "o1", "o3", "o4",
    # DeepSeek R1 family
    "deepseek-r1", "deepseek-reasoner",
    # Qwen 3 thinking
    "qwen3-thinking", "qwq", "-thinking",
    # Kimi k2 thinking
    "kimi-k2-thinking", "kimi-thinking",
    # GLM-Z1
    "glm-z1", "z1-",
)
_REASONING_BASE_URL_HINTS = (
    "stepfun",  # covers *.stepfun.com
    "api.deepseek.com",
    "api.openai.com",  # OpenAI o-series
)


def _looks_like_reasoning_model(model: str, base_url: str = "") -> bool:
    """Return True if ``model`` / ``base_url`` look like a reasoning model
    that defaults to a long planning monologue before its final answer.

    Used to decide whether to auto-inject
    ``extra_body.reasoning_effort="low"`` on non-streaming chat calls.
    """
    m = (model or "").lower()
    if any(hint in m for hint in _REASONING_MODEL_HINTS):
        return True
    b = (base_url or "").lower()
    return any(hint in b for hint in _REASONING_BASE_URL_HINTS)


def _pick_best_content(candidates: list[str]) -> str:
    """Pick the best content string from a list of (main, reasoning, text) candidates.

    Strategy (in order):
      1. If a candidate parses cleanly as a JSON object/array, pick the
         LARGEST such candidate (covers non-reasoning models that put
         the full answer in ``content`` and reasoning models that put a
         tiny stub in ``content`` + the real answer at the end of
         ``reasoning_content``).
      2. Try each candidate's *last balanced JSON object* — reasoning
         models often emit planning prose first, then a JSON object at
         the very end of the stream.
      3. NEW (R15): if all candidates are pure prose (no JSON), try to
         extract just the *answer portion* by looking for markers
         like "以下是正文" / "正文如下" / "好的，". This is the common
         case for step-3.7-flash on the whitedream provider where the
         model dumps everything (planning + answer) into
         ``reasoning_content``.
      4. Last resort: return the largest non-empty candidate as raw
         text (drafter / free-form agents).
    """
    # 1) collect valid JSON candidates with their sizes
    #    Skip JSON STUBS (a tiny envelope like {"content":"这里放内容"} that
    #    reasoning models sometimes emit as a placeholder; the real answer
    #    is in the prose, not the stub). If we returned the stub the
    #    downstream agent would parse a 19-char placeholder and treat it
    #    as the deliverable. Filtering here forces the picker to fall
    #    through to strategy 2 (prose extraction) where the answer lives.
    json_candidates: list[tuple[int, str]] = []
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, (dict, list)) and not _looks_like_json_stub(cand):
                json_candidates.append((len(cand), cand))
        except (json.JSONDecodeError, ValueError):
            pass
    # 1a) full-text trailing-JSON candidates — also skip stubs
    for cand in candidates:
        found = _find_last_json_object(cand)
        if found is not None and not _looks_like_json_stub(found):
            json_candidates.append((len(found), found))
    if json_candidates:
        json_candidates.sort(key=lambda x: x[0], reverse=True)
        return json_candidates[0][1]
    # 2) R15: prose-only candidates — try the answer-extractor on
    #    each. This handles "the model dumped everything into
    #    reasoning_content" (step-3.7-flash on whitedream). The
    #    extractor is conservative: it returns None for short text or
    #    when no marker is found, in which case we fall through to the
    #    raw-text fallback below. We don't impose a min-length here
    #    because the size comparison below is the right tiebreaker —
    #    a short clean answer beats a long planning blob.
    extracted: list[tuple[int, str]] = []
    for cand in candidates:
        answer = _extract_answer_from_prose(cand)
        if answer is not None:
            extracted.append((len(answer), answer))
    if extracted:
        extracted.sort(key=lambda x: x[0], reverse=True)
        return extracted[0][1]
    # 3) raw text fallback: pick the longest non-empty candidate
    return max(candidates, key=len)


class LLMError(Exception):
    """Base error for LLM calls."""


class LLMConnectionError(LLMError):
    pass


class LLMAuthError(LLMError):
    pass


class LLMRateLimitError(LLMError):
    pass


class LLMResponseError(LLMError):
    def __init__(self, message: str, *, raw: str | None = None) -> None:
        super().__init__(message)
        self.raw = raw


@dataclass
class LLMMessage:
    role: str  # system | user | assistant
    content: str


@dataclass
class LLMRequest:
    model: str
    messages: list[LLMMessage]
    temperature: float = 0.8
    max_tokens: int = 2048
    response_format: dict[str, str] | None = None  # {"type": "json_object"}
    extra: dict[str, Any] = field(default_factory=dict)
    # R15: when True (default), use SSE streaming so the first token
    # reaches the caller within 1-5s instead of waiting 30-60s for the
    # full non-streaming response. The cost / output_tokens / content
    # shape are identical — only the delivery mechanism differs. The
    # picker still runs at the end so behaviour is unchanged.
    stream: bool = True


@dataclass
class LLMCallResult:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: int
    raw: dict[str, Any]


class LLMClient:
    """Stateless OpenAI-Compatible client. Reuse the instance across calls."""

    def __init__(self, *, timeout: float | None = None) -> None:
        # Layered timeout: fail fast on TCP/TLS (15s) and pool wait, but
        # give the actual read of the LLM response the full budget. Slow
        # providers (e.g. reasoning models) can easily take 60-180s for a
        # 2-4K-token reply — a single 120s read timeout causes spurious
        # ReadTimeouts on otherwise-healthy calls.
        read_timeout = timeout or settings.llm_default_timeout_seconds
        connect_timeout = settings.llm_connect_timeout_seconds
        self.timeout = httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=connect_timeout,
            pool=connect_timeout,
        )
        self.read_timeout_seconds = read_timeout
        self.max_retries = settings.llm_max_retries
        self._client = httpx.AsyncClient(timeout=self.timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_models(self, base_url: str, api_key: str) -> list[str]:
        # local mock: surface a fixed set
        if base_url.startswith("mock://"):
            return ["mock-fast", "mock-long", "mock-vision"]
        url = self._join_url(base_url, "models")
        # ``/models`` is a fast metadata call. Cap the read at 15s so a
        # misconfigured base_url (e.g. pointing at a chat-only host, a
        # slow proxy, or a 5xx-loop) can't burn the full 600s chat budget
        # and freeze the UI's 「测试连接」 button — a 15s hang already
        # makes the user think the page went black.
        short_timeout = httpx.Timeout(
            connect=self.timeout.connect,
            read=15.0,
            write=self.timeout.write,
            pool=self.timeout.pool,
        )
        try:
            resp = await self._client.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=short_timeout,
            )
        except httpx.HTTPError as exc:
            logger.error("list_models httpx error url=%s err=%s", url, _fmt_exc(exc))
            raise LLMConnectionError(f"无法连接 {url}: {_fmt_exc(exc)}") from exc
        if resp.status_code == 401:
            raise LLMAuthError("401 Unauthorized: API Key 无效")
        if resp.status_code >= 400:
            raise LLMResponseError(
                f"获取模型列表失败: HTTP {resp.status_code} {resp.text[:200]}"
            )
        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise LLMResponseError(f"模型列表响应非 JSON: {resp.text[:200]}") from exc
        items = data.get("data") or []
        names: list[str] = []
        for item in items:
            mid = item.get("id") or item.get("model") or item.get("name")
            if mid:
                names.append(str(mid))
        return names

    async def chat(
        self,
        *,
        base_url: str,
        api_key: str,
        request: LLMRequest,
        provider_extra: dict[str, Any] | None = None,
    ) -> LLMCallResult:
        # local mock mode: deterministic, no network, used for offline dev
        if base_url.startswith("mock://"):
            return self._mock_chat(base_url, request)
        url = self._join_url(base_url, "chat/completions")
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [m.__dict__ for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.response_format:
            payload["response_format"] = request.response_format
        if request.extra:
            payload.update(request.extra)

        retrying = AsyncRetrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type((LLMConnectionError, LLMRateLimitError)),
            reraise=True,
        )

        try:
            async for attempt in retrying:
                with attempt:
                    if request.stream:
                        return await self._do_chat_stream(
                            url, api_key, payload, request.model, base_url,
                            provider_extra=provider_extra,
                        )
                    return await self._do_chat(
                        url, api_key, payload, request.model, base_url, provider_extra=provider_extra
                    )
        except LLMAuthError:
            raise
        except LLMResponseError:
            raise
        except LLMConnectionError:
            raise
        except Exception as exc:  # pragma: no cover
            logger.exception("chat unexpected error url=%s model=%s", url, request.model)
            raise LLMConnectionError(f"调用失败: {_fmt_exc(exc)}") from exc

    async def _do_chat_stream(
        self,
        url: str,
        api_key: str,
        payload: dict[str, Any],
        model: str,
        base_url: str = "",
        *,
        provider_extra: dict[str, Any] | None = None,
    ) -> LLMCallResult:
        """SSE streaming variant of :meth:`_do_chat`.

        Sends ``stream: true`` + ``stream_options.include_usage`` to the
        provider, iterates the SSE chunks, accumulates ``delta.content``
        and ``delta.reasoning_content``, then runs the same picker on
        the joined result. Identical behaviour to the non-streaming
        path from the caller's perspective — only the TTFT improves.
        """
        # Reuse the system-message + extra_body injection from _do_chat
        # so the two paths stay in lockstep. We extract that into a
        # helper so the streaming branch can call it before opening the
        # connection.
        payload = self._prepare_payload(payload, model, base_url, provider_extra)
        payload["stream"] = True
        # The provider emits a final ``choices: []`` chunk whose only
        # field is ``usage`` — ``include_usage: true`` makes that
        # actually arrive (otherwise usage is missing on streamed calls).
        payload["stream_options"] = {"include_usage": True}

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        t0 = time.perf_counter()
        # httpx per-request timeout for the *whole* streamed response.
        # The client's pooled timeouts only apply until the first byte;
        # the read budget needs to cover the entire generation.
        try:
            async with self._client.stream(
                "POST", url, headers=headers, json=payload, timeout=self.timeout
            ) as resp:
                if resp.status_code == 401:
                    raise LLMAuthError("401 Unauthorized: API Key 无效")
                if resp.status_code == 429:
                    body = await resp.aread()
                    raise LLMRateLimitError(f"429 限流: {body[:200].decode('utf-8', 'ignore')}")
                if resp.status_code >= 500:
                    body = await resp.aread()
                    raise LLMConnectionError(
                        f"上游服务异常 HTTP {resp.status_code}: {body[:200].decode('utf-8', 'ignore')}"
                    )
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise LLMResponseError(
                        f"调用失败 HTTP {resp.status_code}: {body[:200].decode('utf-8', 'ignore')}"
                    )

                content_chunks: list[str] = []
                reasoning_chunks: list[str] = []
                usage: dict[str, Any] = {}
                response_model: str = model
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        # Some providers send ``event:`` / heartbeat
                        # lines we don't care about.
                        continue
                    payload_str = line[6:].strip()
                    if payload_str == "[DONE]":
                        break
                    try:
                        evt = json.loads(payload_str)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(evt.get("model"), str):
                        response_model = evt["model"]
                    choice = (evt.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    c = delta.get("content")
                    if isinstance(c, str) and c:
                        content_chunks.append(c)
                    r = delta.get("reasoning_content")
                    if isinstance(r, str) and r:
                        reasoning_chunks.append(r)
                    # The final chunk has empty ``choices`` and the
                    # usage block. Capture it.
                    if not choice and isinstance(evt.get("usage"), dict):
                        usage = evt["usage"]
        except httpx.HTTPError as exc:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            logger.error(
                "_do_chat_stream httpx error url=%s model=%s elapsed_ms=%d err=%s",
                url, model, elapsed_ms, _fmt_exc(exc),
            )
            raise LLMConnectionError(f"无法连接 {url}: {_fmt_exc(exc)}") from exc

        duration_ms = int((time.perf_counter() - t0) * 1000)
        main = "".join(content_chunks)
        reasoning = "".join(reasoning_chunks)
        if not main and not reasoning:
            raise LLMResponseError("模型流式返回空内容")

        candidates: list[str] = []
        for cand in (main, reasoning):
            cand = cand.strip() if isinstance(cand, str) else ""
            if cand:
                candidates.append(cand)
        content = _pick_best_content(candidates)

        input_tokens = int(usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or 0)
        cost = estimate_cost_usd(model, input_tokens, output_tokens)
        # Build a synthetic raw response that mirrors the non-streaming
        # shape — downstream code (worker logs, debugging, etc.) sees
        # the same structure regardless of which path was used.
        raw = {
            "id": None,
            "object": "chat.completion",
            "model": response_model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": main,
                        "reasoning_content": reasoning,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": usage,
            "_streamed": True,
        }
        return LLMCallResult(
            content=content,
            model=response_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            duration_ms=duration_ms,
            raw=raw,
        )

    def _prepare_payload(
        self,
        payload: dict[str, Any],
        model: str,
        base_url: str,
        provider_extra: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Shared system-message + extra_body injection for the two
        transport paths (streaming and non-streaming).

        Extracted so the streaming branch can call it without
        duplicating the system-reminder + ``reasoning_effort``
        auto-inject logic. See :meth:`_do_chat` for the full story.
        """
        messages = payload.get("messages") or []
        has_system = any(m.get("role") == "system" for m in messages)
        strict_system = (
            "你是文本生成助手。严格遵守以下规则：\n"
            "1. 直接给出最终答案，不要输出思考过程、推理步骤或自问自答。\n"
            "2. 如果任务要求返回 JSON，你必须只输出一个合法 JSON 对象，"
            "   以 { 开头、} 结尾，不要任何前缀文字、解释、Markdown 标记、"
            "   ```json 围栏、注释或后置说明。\n"
            "3. 任何不在 JSON 内的文字都会导致任务失败。"
        )
        if not has_system:
            messages = [{"role": "system", "content": strict_system}] + messages
        else:
            messages = [
                {
                    "role": "system",
                    "content": strict_system
                    + "\n\n（以上规则优先于用户消息中的格式说明）",
                }
            ] + messages
        if messages and messages[-1].get("role") == "user":
            tail = messages[-1]
            extra = (
                "\n\n[系统提醒] 只输出一个 JSON 对象，"
                "以 { 开头、} 结尾，不要任何其他文字。"
            )
            tail = {**tail, "content": (tail.get("content") or "") + extra}
            messages = messages[:-1] + [tail]
        payload = {**payload, "messages": messages}
        pe = provider_extra or {}
        if pe.get("inject_reasoning_effort"):
            payload.setdefault(
                "extra_body",
                {
                    "reasoning_effort": pe.get("reasoning_effort", "low")
                },
            )
        elif not pe.get("no_auto_reasoning_effort") and _looks_like_reasoning_model(model, base_url):
            payload.setdefault(
                "extra_body",
                {"reasoning_effort": pe.get("reasoning_effort", "low")},
            )
        return payload

    async def _do_chat(
        self,
        url: str,
        api_key: str,
        payload: dict[str, Any],
        model: str,
        base_url: str = "",
        *,
        provider_extra: dict[str, Any] | None = None,
    ) -> LLMCallResult:
        # Inject the strict system message + auto reasoning_effort (see
        # ``_prepare_payload`` for the rationale). Identical to the
        # streaming branch — both paths converge on the same payload.
        payload = self._prepare_payload(payload, model, base_url, provider_extra)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        t0 = time.perf_counter()
        try:
            resp = await self._client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            logger.error(
                "_do_chat httpx error url=%s model=%s elapsed_ms=%d err=%s",
                url,
                model,
                elapsed_ms,
                _fmt_exc(exc),
            )
            raise LLMConnectionError(f"无法连接 {url}: {_fmt_exc(exc)}") from exc
        duration_ms = int((time.perf_counter() - t0) * 1000)

        if resp.status_code == 401:
            raise LLMAuthError("401 Unauthorized: API Key 无效")
        if resp.status_code == 429:
            raise LLMRateLimitError(f"429 限流: {resp.text[:200]}")
        if resp.status_code >= 500:
            raise LLMConnectionError(
                f"上游服务异常 HTTP {resp.status_code}: {resp.text[:200]}"
            )
        if resp.status_code >= 400:
            raise LLMResponseError(
                f"调用失败 HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise LLMResponseError(
                f"响应非 JSON: {resp.text[:200]}", raw=resp.text
            ) from exc

        choices = data.get("choices") or []
        if not choices:
            raise LLMResponseError(
                f"响应缺少 choices: {json.dumps(data)[:200]}", raw=resp.text
            )

        message = choices[0].get("message") or {}
        # Some reasoning models (step-3.7-flash, deepseek-r1, o1, ...) put
        # the actual answer in `reasoning_content` while `content` is empty.
        # Other variants (or even the same model on different prompts) put
        # the answer in `content` and the thinking in `reasoning_content`.
        # We try multiple fields, prefer whichever one looks like the
        # final structured answer (a JSON object at the END of the stream,
        # since reasoning models tend to plan first then emit the answer).
        main = (message.get("content") or "")
        reasoning = (message.get("reasoning_content") or "")
        # some providers also dump answer in a top-level `text` field
        fallback = (choices[0].get("text") or "")
        candidates: list[str] = []
        for cand in (main, reasoning, fallback):
            cand = cand.strip() if isinstance(cand, str) else ""
            if cand:
                candidates.append(cand)
        if not candidates:
            raise LLMResponseError("模型返回空内容", raw=resp.text)
        content = _pick_best_content(candidates)

        usage = data.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or 0)
        cost = estimate_cost_usd(model, input_tokens, output_tokens)
        return LLMCallResult(
            content=content,
            model=data.get("model", model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            duration_ms=duration_ms,
            raw=data,
        )

    @staticmethod
    def _join_url(base_url: str, path: str) -> str:
        base = base_url.rstrip("/")
        return f"{base}/{path.lstrip('/')}"

    # ---- mock LLM (offline dev) ----
    def _mock_chat(self, base_url: str, request: LLMRequest) -> LLMCallResult:
        """Return deterministic JSON-ish text per agent role.

        Activated when `base_url` starts with `mock://`. Used to develop UI /
        test pipelines without spending API credits. The replies are
        intentionally simple: the system *runs* end-to-end but the prose is
        clearly placeholder. Replace the provider with a real one in
        "模型配置" once you have a key.
        """
        import hashlib
        joined = "\n".join(m.content for m in request.messages)
        h = hashlib.md5(joined.encode("utf-8")).hexdigest()
        # pick a reply template by inspecting the first user message for known
        # agent markers — fall back to a generic placeholder.
        text = request.messages[-1].content if request.messages else ""
        # detect agent by Chinese role marker in the prompt body (each agent
        # template opens with a distinct "你是 XX" / "请对 XX" line).
        role_hint = ""
        marker_map = {
            "章节规划师": "planner",
            "正文写手": "draft",
            "综合审核员": "critic",
            "改稿编辑": "rewriter",
            "连续性检查": "continuity",
            "记忆的事实": "memoryupdate",
            "学习复盘": "learning",
            "总编 + 调度器": "chief",
            "识别人物": "study",
            "行为模式卡": "behaviorpattern",
        }
        for marker, hint in marker_map.items():
            if marker in text:
                role_hint = hint
                break
        if not role_hint:
            # English fallback (e.g. if someone edits the prompt to English)
            lower = text.lower()
            for marker in ("planneragent", "draftagent", "criticagent",
                           "rewriteragent", "continuityagent",
                           "memoryupdateagent", "learningagent", "chiefagent",
                           "studyagent", "behaviorpatternagent"):
                if marker in lower:
                    role_hint = marker.replace("agent", "")
                    break
        template = _MOCK_REPLIES.get(role_hint, _MOCK_REPLIES["default"])
        # templates contain literal JSON braces, so swap in our placeholders
        # with simple string replacement rather than str.format.
        content = (
            template
            .replace("{hash}", h[:6])
            .replace("{placeholder}", text[:60].replace("\n", " "))
            .replace("{h}", h)
        )
        in_tok = max(1, len(joined) // 4)
        out_tok = max(1, len(content) // 4)
        cost = estimate_cost_usd(request.model, in_tok, out_tok)
        return LLMCallResult(
            content=content,
            model=request.model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
            duration_ms=80 + (int(h[:2], 16) % 200),
            raw={"mock": True, "base_url": base_url, "role_hint": role_hint},
        )


_MOCK_PLANNER = """{
  "summary": "本章围绕主角在宗门被逐出后意外发现体内残玉的转折，重点刻画心境转变与伏笔布置。",
  "beats": [
    {"name": "开场", "purpose": "建立场景：落魄离开山门，阴雨，小师妹远远目送。", "target_words": 600},
    {"name": "触发", "purpose": "跌入山谷，意外发现体内残玉。", "target_words": 800},
    {"name": "中段", "purpose": "残玉第一次与意识对话，提示一段模糊的远古口诀。", "target_words": 900},
    {"name": "收束", "purpose": "主角做出选择：暂不返回宗门，先以散修身份寻找残玉来历。", "target_words": 700}
  ],
  "scenes": ["山门外", "谷底", "山洞内"],
  "characters_in_scene": ["沈落", "小师妹(仅回忆)"],
  "foreshadow_to_plant": ["残玉来历", "远古口诀"],
  "open_threads_to_address": [],
  "tone": "沉郁、克制、留白"
}"""

_MOCK_DRAFTER = """{
  "content": "山门外，雨水沿着青石阶一层层漫下来。沈落把外袍解下来，叠好放在山门前的石狮子上，抬脚迈过那条他走了十八年的门槛。\\n\\n没有人送他。\\n\\n他听见身后有脚步声想要跟出来，又停住了。他没有回头，只把头压得更低。\\n\\n跌入谷底的时候，胸口那块残玉忽然烫了一下。\\n\\n他抬手按住，掌心传来的温度像是一种安抚，又像是一种提醒。",
  "foreshadow_planted": ["残玉来历"],
  "characters_present": ["沈落"]
}"""

_MOCK_CRITIC = """{
  "total": 78,
  "scores": {
    "plot_continuity": 80,
    "character_consistency": 78,
    "writing_quality": 80,
    "rhythm": 76,
    "dialogue": 78,
    "foreshadow_density": 75
  },
  "issues": [
    {"category": "rhythm", "severity": "low", "quote": "雨水沿着青石阶", "comment": "中段节奏略快，建议补一笔残玉的来源铺垫。"}
  ],
  "rewrite_required": false,
  "summary": "本章达到及格线。结构完整，情绪克制，可发布。",
  "next_chapter_hook": "沈落把残玉握紧了一寸，远处有人在等他。"
}"""

_MOCK_REWRITER = """{
  "rewritten_content": "山门外，雨水沿着青石阶一层层漫下来。沈落把外袍解下来，叠好放在山门前的石狮子上。他最后看了一眼那座走了十八年的山门，没有回头。\\n\\n跌入谷底的时候，胸口那块残玉忽然烫了一下。\\n\\n他抬手按住，掌心传来的温度像是一种安抚，又像是一种提醒。",
  "changes": [
    {"before": "中段节奏略快", "after": "补了残玉的来源", "reason": "修复 critic 提到的节奏问题"}
  ]
}"""

_MOCK_CONTINUITY = """{
  "hard_conflicts": [],
  "soft_warnings": ["小师妹未出场但被回忆提及，建议下一章补一段对位。"],
  "foreshadow_misses": [],
  "score": 82,
  "verdict": "pass"
}"""

_MOCK_MEMORY = """{
  "characters": [
    {"name": "沈落", "state_update": {"current_location": "落雁谷", "emotion_state": "沉郁", "owned_items": ["残玉"]}}
  ],
  "foreshadows": [
    {"name": "残玉来历", "status": "active", "importance": 0.7, "planted_chapter": 1}
  ],
  "hard_facts": [
    {"category": "setting", "fact": "沈落被青云宗外门除名。", "source_chapter": 1}
  ]
}"""

_MOCK_LEARNER = """{
  "insights": [
    "本章读者反馈偏正向：'落笔克制'，可延续。",
    "伏笔密度略低，下一章补一条关于残玉口诀的暗示。"
  ],
  "user_pref_updates": {"preferred_pace": "slow-burn"},
  "next_chapter_suggestion": "把残玉口诀的暗示放进来，但不要解释太清楚。"
}"""

_MOCK_CHIEF = """{
  "reply": "我已查看当前项目状态。要不要我现在就启动 Worker，让它按设定的目标日更自动续写？",
  "actions": [
    {"action_id": "start_worker", "type": "start_worker", "label": "启动 Worker", "description": "让后台按当前策略持续写下一章。", "params": {}, "requires_confirm": false}
  ],
  "thinking": "用户可能想要让系统自动跑起来。",
  "learning_notice": null
}"""

_MOCK_STUDY = """{
  "characters": [],
  "study_note": "Mock 占位返回。生产请在「模型配置」把 StudyAgent 角色绑定到真实 Provider，否则会一直返回空 list。",
  "mock": true
}"""

_MOCK_BEHAVIOR = """{
  "patterns": [
    {"tag": "逆境觉醒", "trigger": "被抛弃", "action": "偶得异宝", "weight": 0.8, "example": "落魄出山门"}
  ]
}"""

_MOCK_DEFAULT = """{
  "note": "这是 mock LLM 的占位回复（hash={hash}）。请在「模型配置」页配置真实 Provider。",
  "echo_first_chars": "{placeholder}"
}"""

_MOCK_REPLIES: dict[str, str] = {
    "planner": _MOCK_PLANNER,
    "draft": _MOCK_DRAFTER,
    "critic": _MOCK_CRITIC,
    "rewriter": _MOCK_REWRITER,
    "continuity": _MOCK_CONTINUITY,
    "memoryupdate": _MOCK_MEMORY,
    "learning": _MOCK_LEARNER,
    "learner": _MOCK_LEARNER,
    "chief": _MOCK_CHIEF,
    "study": _MOCK_STUDY,
    "behaviorpattern": _MOCK_BEHAVIOR,
    "default": _MOCK_DEFAULT,
}


_client_singleton: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = LLMClient()
    return _client_singleton
