"""OpenAI-Compatible chat completions client (spec §1.3).

Works with any provider that exposes `POST {base_url}/chat/completions` and
optionally `GET {base_url}/models` (OpenAI, OpenRouter, DeepSeek, Claude and
Gemini proxies, vLLM, Ollama, etc.).
"""
from __future__ import annotations

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


def _pick_best_content(candidates: list[str]) -> str:
    """Pick the best content string from a list of (main, reasoning, text) candidates.

    Strategy:
      1. If a candidate is a parseable JSON object/array AND is the LARGEST
         such candidate, use it (the model respected the JSON contract and
         the answer is the full-sized object — common for non-reasoning
         models and `kimi-k2.6` / `deepseek-v4-flash`).
      2. Otherwise, prefer the candidate whose largest trailing JSON object
         is the LARGEST (reasoning models often put a tiny stub in
         ``content`` and the real answer at the END of ``reasoning_content``).
      3. Otherwise, return the largest non-empty candidate as raw text
         (drafter / free-form agents).
    """
    # 1) collect valid JSON candidates with their sizes
    json_candidates: list[tuple[int, str]] = []
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, (dict, list)):
                json_candidates.append((len(cand), cand))
        except (json.JSONDecodeError, ValueError):
            pass
    # 1a) full-text trailing-JSON candidates
    for cand in candidates:
        found = _find_last_json_object(cand)
        if found is not None:
            json_candidates.append((len(found), found))
    if json_candidates:
        # pick the LARGEST valid JSON we found (size = bytes of the
        # JSON text, not the parsed object). This handles both:
        #  - non-reasoning models that put the full answer in `content`
        #  - reasoning models that put a tiny stub in `content` and the
        #    real answer at the end of `reasoning_content`
        json_candidates.sort(key=lambda x: x[0], reverse=True)
        return json_candidates[0][1]
    # 2) raw text fallback: pick the longest non-empty candidate
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
        try:
            resp = await self._client.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
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
                    return await self._do_chat(
                        url, api_key, payload, request.model, provider_extra=provider_extra
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

    async def _do_chat(
        self,
        url: str,
        api_key: str,
        payload: dict[str, Any],
        model: str,
        *,
        provider_extra: dict[str, Any] | None = None,
    ) -> LLMCallResult:
        # Inject a hard system message that:
        #   1) forces reasoning models (step-3.7-flash, deepseek-r1, o1, ...)
        #      to skip their internal "thinking" preamble, and
        #   2) forbids any non-JSON prose around JSON output, since small
        #      models on this provider tend to comply weakly with
        #      `response_format=json_object` and emit explanations like
        #      "用户需要的是..." first.
        # We also append a no-think reminder to the last user message so
        # the instruction survives any system-prompt-stripping the
        # provider might do.
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
            # keep any caller-provided system message, but reinforce it
            messages = [
                {
                    "role": "system",
                    "content": strict_system
                    + "\n\n（以上规则优先于用户消息中的格式说明）",
                }
            ] + messages
        # belt-and-suspenders: append a tiny reminder to the tail so the
        # model sees the JSON rule at the very end of the prompt too.
        if messages and messages[-1].get("role") == "user":
            tail = messages[-1]
            extra = (
                "\n\n[系统提醒] 只输出一个 JSON 对象，"
                "以 { 开头、} 结尾，不要任何其他文字。"
            )
            tail = {**tail, "content": (tail.get("content") or "") + extra}
            messages = messages[:-1] + [tail]
        payload["messages"] = messages
        # P0-5 fix: ``extra_body`` is a vLLM/sglang/StepFun convention,
        # NOT a standard OpenAI field. Sending it to a strict OpenAI-
        # compatible proxy triggers 400/422. We now only inject it when
        # the Provider has explicitly opted in via its ``extra`` JSON
        # column, e.g.:
        #   {"inject_reasoning_effort": true, "reasoning_effort": "low"}
        # Default providers (incl. anything pointing at openai.com)
        # get a clean request with no extra_body.
        if provider_extra and provider_extra.get("inject_reasoning_effort"):
            payload.setdefault(
                "extra_body",
                {
                    "reasoning_effort": provider_extra.get("reasoning_effort", "low")
                },
            )
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
  "book_title": "示例拆书",
  "world_rules": ["修炼以灵根为根", "宗门有外门内门之别"],
  "character_archetypes": [{"name": "废脉主角", "tags": ["隐忍", "成长"], "description": "天生废脉却暗藏奇物"}],
  "scene_kits": [{"name": "宗门除名", "scenes": ["大殿宣告", "弟子目送"]}],
  "behavior_patterns": [{"tag": "逆境觉醒", "when": "被宗门抛弃", "then": "偶得异宝"}]
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
