"""LLM Provider 运行时配置覆盖层。

对应工程方案：
- 第 41 节 LLM Provider 架构（API Key 只允许后端保存）
- 第 42 节 模型分层

设计：
- .env 仍然是基础配置；本模块提供「运行时覆盖」，持久化到
  data/llm_config.json（已随 data/ 目录留在本地，不入库 git 时需自行注意）。
- 读取优先级：覆盖层 > .env。覆盖层任一字段为空字符串表示「该字段沿用 .env」。
- API Key 永不完整下发前端：GET 接口只返回脱敏形式（前 3 + 后 4）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from app.config import ProviderSettings, get_settings

Tier = Literal["reasoning", "cheap", "vision"]
TIERS: tuple[Tier, ...] = ("reasoning", "cheap", "vision")

_OVERRIDE_PATH = Path("data/llm_config.json")


def load_overrides() -> dict[str, dict[str, str]]:
    """读取覆盖配置。文件不存在/损坏时返回空。"""
    if not _OVERRIDE_PATH.exists():
        return {}
    try:
        data = json.loads(_OVERRIDE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        tier: {k: str(v) for k, v in fields.items() if isinstance(v, str)}
        for tier, fields in data.items()
        if tier in TIERS and isinstance(fields, dict)
    }


def save_overrides(overrides: dict[str, dict[str, str]]) -> None:
    _OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OVERRIDE_PATH.write_text(
        json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def update_tier(
    tier: Tier,
    *,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> None:
    """更新某一层的覆盖配置。None = 不动该字段；空字符串 = 清除覆盖（回退 .env）。"""
    overrides = load_overrides()
    fields = overrides.setdefault(tier, {})
    for key, value in (("base_url", base_url), ("model", model), ("api_key", api_key)):
        if value is None:
            continue
        if value == "":
            fields.pop(key, None)
        else:
            fields[key] = value
    if not fields:
        overrides.pop(tier, None)
    save_overrides(overrides)


def clear_tier(tier: Tier) -> None:
    overrides = load_overrides()
    if tier in overrides:
        overrides.pop(tier)
        save_overrides(overrides)


def effective_provider(tier: Tier) -> ProviderSettings:
    """覆盖层 > .env 合并后的有效配置。Provider 工厂应统一走这里。"""
    env = get_settings().provider(tier)
    ov = load_overrides().get(tier, {})
    return ProviderSettings(
        base_url=ov.get("base_url") or env.base_url,
        api_key=ov.get("api_key") or env.api_key,
        model=ov.get("model") or env.model,
    )


def mask_key(key: str) -> str:
    """脱敏：只露前 3 后 4，中间打码。空 key 返回空串。"""
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "****"
    return f"{key[:3]}****{key[-4:]}"


def describe() -> dict[str, dict[str, object]]:
    """给前端的只读视图（key 已脱敏）。"""
    overrides = load_overrides()
    out: dict[str, dict[str, object]] = {}
    for tier in TIERS:
        env = get_settings().provider(tier)
        ov = overrides.get(tier, {})
        eff = effective_provider(tier)
        out[tier] = {
            "base_url": eff.base_url,
            "model": eff.model,
            "api_key_masked": mask_key(eff.api_key),
            "has_api_key": bool(eff.api_key),
            "configured": eff.configured,
            # override 中的字段来源标记，前端用来提示「此项来自页面配置」
            "overridden_fields": sorted(ov.keys()),
        }
    return out
