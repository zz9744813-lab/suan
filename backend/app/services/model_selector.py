"""P1-Model-Failover: 模型选择服务.

给定 agent_role_key / legacy_role, 返回最佳 ResolvedModel.
支持 auto / manual / manual_with_fallback 三种模式.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_role import AgentModelBinding, AgentRole
from app.models.model_call_event import ModelCallEvent
from app.models.model_provider import ModelProvider
from app.models.model_runtime import ModelRuntimeStat
from app.services.model_capability import (
    AGENT_CAPABILITY_PROFILE,
    LEGACY_ROLE_TO_AGENT_KEY,
    STRATEGY_WEIGHTS,
)

logger = logging.getLogger(__name__)


# ── 数据结构 ──────────────────────────────────────────────

@dataclass
class ModelCandidate:
    """一个候选模型的评分结果."""
    provider_id: int
    provider_name: str
    base_url: str
    api_key: str
    model_name: str
    score: float
    reason: str
    temperature: float | None = None
    max_tokens: int | None = None
    extra_body: dict[str, Any] | None = None
    # 评分明细
    health: float | None = None
    success_rate: float | None = None
    latency_ms: int | None = None
    cost_score: float | None = None
    risk: list[str] = field(default_factory=list)


@dataclass
class SelectedModel:
    """ModelSelector.select_for_agent 的返回值."""
    provider: ModelProvider
    model_name: str
    temperature: float
    max_tokens: int
    extra_body: dict[str, Any] | None
    selection_mode: str
    selection_score: float
    selection_reason: str
    candidates: list[ModelCandidate]


# ── 评分函数 ──────────────────────────────────────────────

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def provider_health_score(p: ModelProvider) -> float:
    if p.circuit_state == "open":
        # 检查 half_open
        if p.circuit_open_until and p.circuit_open_until <= datetime.utcnow():
            return 0.3  # half_open, 给低分但允许探针
        return 0.0

    base = p.health_score or 0.75

    if p.last_health_status == "failed":
        base -= 0.25

    if p.consecutive_failures >= 2:
        base -= 0.15 * min(p.consecutive_failures, 5)

    if p.success_rate_1h is not None and p.success_rate_1h < 1.0:
        base = base * 0.5 + p.success_rate_1h * 0.5

    return _clamp(base)


def latency_score(avg_latency_ms: int | None) -> float:
    if not avg_latency_ms:
        return 0.7
    if avg_latency_ms <= 1500:
        return 1.0
    if avg_latency_ms <= 4000:
        return 0.8
    if avg_latency_ms <= 9000:
        return 0.55
    if avg_latency_ms <= 20000:
        return 0.3
    return 0.1


def cost_score(model_name: str) -> float:
    """从 model 名推断成本分 (简化版, 后续可接 pricing.py)."""
    name = model_name.lower()
    # 免费或极低价模型
    for kw in ("mini", "flash", "lite", "tiny", "small", "cheap"):
        if kw in name:
            return 1.0
    # 中等
    for kw in ("pro", "plus", "v3", "4o", "sonnet"):
        if kw in name:
            return 0.6
    # 高价
    for kw in ("opus", "o1", "o3", "max", "ultra"):
        if kw in name:
            return 0.25
    return 0.65


def provider_priority_score(p: ModelProvider) -> float:
    """Prefer user-configured API providers over local/mock fallbacks."""
    base_url = (p.base_url or "").lower()
    name = (p.name or "").lower()
    if base_url.startswith("mock://") or name in {"stub", "mock"}:
        return 0.0
    if "localhost" in base_url or "127.0.0.1" in base_url or base_url.startswith("http://local"):
        return 0.35
    if p.api_key:
        return 1.0
    return 0.55


def model_power_score(model_name: str) -> float:
    """Rough model-size / quality heuristic from the public model name."""
    name = model_name.lower()
    premium = (
        "opus", "o3", "o1", "ultra", "max", "sonnet", "gpt-4.1", "gpt-4o",
        "deepseek-reasoner", "gemini-2.5-pro", "claude-3.5", "claude-3-5",
    )
    strong = ("pro", "v3", "72b", "70b", "32b", "qwen-max", "reasoner")
    small = ("mini", "flash", "lite", "tiny", "small", "8b", "7b", "3b")
    if any(k in name for k in premium):
        return 1.0
    if any(k in name for k in strong):
        return 0.78
    if any(k in name for k in small):
        return 0.42
    return 0.62


def role_quality_need(profile: dict, role_key: str) -> float:
    """High-risk creative/reasoning roles should get stronger models."""
    low_risk_roles = {"reader_hook", "comment_triage", "memory_update", "learner"}
    if role_key in low_risk_roles:
        return 0.35
    signals = [
        float(profile.get("needs_reasoning") or 0),
        float(profile.get("needs_style") or 0),
        float(profile.get("needs_creativity") or 0),
        0.85 if profile.get("needs_long_output") else 0.0,
        0.75 if profile.get("needs_long_context") else 0.0,
    ]
    return _clamp(max(signals) if signals else 0.6, 0.35, 0.95)


def text_role_modality_penalty(role_key: str, model_name: str) -> float:
    """Penalize multimodal-specialty models for normal text agents."""
    role = (role_key or "").lower()
    if any(k in role for k in ("image", "vision", "video", "audio")):
        return 0.0
    name = (model_name or "").lower()
    if any(k in name for k in ("video", "t2v", "i2v")):
        return 0.35
    if any(k in name for k in ("vision", "image", "audio", "asr", "tts", "speech", "whisper")):
        return 0.28
    if any(k in name for k in ("-vl", "_vl", ".vl", "/vl")):
        return 0.28
    return 0.0


def is_text_role_model_compatible(role_key: str, model_name: str) -> bool:
    """Return False when a normal text role is pointed at a media model."""
    return text_role_modality_penalty(role_key, model_name) == 0.0


def _usable_runtime_stat(stats: Any) -> bool:
    """Return True only for runtime stat objects with numeric counters."""
    if stats is None:
        return False
    total_calls = getattr(stats, "total_calls", None)
    success_calls = getattr(stats, "success_calls", None)
    return isinstance(total_calls, (int, float)) and isinstance(success_calls, (int, float))


_MODEL_LOCAL_FAILURE_TYPES = {"model_not_found", "timeout", "empty_response", "json_parse_failed"}
_PROVIDER_WIDE_FAILURE_TYPES = {"auth_error", "rate_limited", "budget_exhausted", "connection_error", "server_error"}


def _should_skip_open_provider(provider: ModelProvider) -> bool:
    """Only provider-wide failures should remove every model on that provider."""
    if provider.circuit_state != "open":
        return False
    if provider.circuit_open_until and provider.circuit_open_until <= datetime.utcnow():
        return False
    raw_failure_type = getattr(provider, "last_failure_type", None)
    failure_type = raw_failure_type if isinstance(raw_failure_type, str) else ""
    if failure_type in _MODEL_LOCAL_FAILURE_TYPES:
        return False
    return failure_type in _PROVIDER_WIDE_FAILURE_TYPES or not failure_type


async def _recent_model_failure(
    db: AsyncSession,
    provider_id: int,
    model_name: str,
) -> str | None:
    row = (await db.execute(
        select(ModelCallEvent).where(
            and_(
                ModelCallEvent.provider_id == provider_id,
                ModelCallEvent.model_name == model_name,
                ModelCallEvent.failure_type.in_(_MODEL_LOCAL_FAILURE_TYPES),
            )
        ).order_by(ModelCallEvent.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    failure_type = getattr(row, "failure_type", None) if row else None
    return failure_type if isinstance(failure_type, str) else None


def json_stability_score(stats: ModelRuntimeStat | None) -> float:
    if stats is None or stats.total_calls < 5:
        return 0.7
    return _clamp(1 - stats.json_parse_failures / max(stats.total_calls, 1))


def capability_match(
    profile: dict,
    provider: ModelProvider,
    model_name: str,
    stats: ModelRuntimeStat | None,
) -> float:
    score = 0.5
    tags: list[str] = []
    # 从 last_health_full 获取 recommended_roles
    hf = provider.last_health_full or {}
    model_results = hf.get("model_results", {})
    mr = model_results.get(model_name, {})
    recommended = mr.get("recommended_roles", [])
    if recommended:
        tags = recommended

    # 从 model_list 推断
    model_lower = model_name.lower()
    if "json" in tags or profile.get("needs_json"):
        if profile.get("needs_json") and ("json" in tags or "json" in model_lower):
            score += 0.2

    if profile.get("needs_long_output") and ("longform" in tags or "long" in model_lower):
        score += 0.2

    if profile.get("needs_reasoning", 0) > 0.8 and ("reasoning" in tags or "reason" in model_lower):
        score += 0.15

    if profile.get("needs_speed", 0) > 0.7 and stats and stats.avg_latency_ms and stats.avg_latency_ms < 3000:
        score += 0.15

    return _clamp(score)


# ── 主服务类 ──────────────────────────────────────────────

class ModelSelectorService:
    """根据 Agent 角色、策略、运行统计自动选择最佳模型."""

    async def select_for_agent(
        self,
        db: AsyncSession,
        *,
        agent_role_key: str,
        legacy_role: str | None = None,
        project_id: int | None = None,
        task_id: int | None = None,
        force_fallback: bool = False,
    ) -> SelectedModel:
        """为 Agent 选择最佳模型.

        Args:
            force_fallback: 主模型失败后强制走 fallback
        """
        # 1. 找 AgentRole + Binding
        role_key = agent_role_key
        if not role_key and legacy_role:
            role_key = LEGACY_ROLE_TO_AGENT_KEY.get(legacy_role, legacy_role)

        role, binding = await self._get_role_and_binding(db, role_key)
        mode = binding.selection_mode if binding else "auto"
        strategy = binding.auto_strategy if binding else "quality_first"

        if force_fallback and mode == "manual":
            if binding and binding.allow_auto_fallback:
                mode = "manual_with_fallback"
            else:
                raise ValueError(f"Agent {role_key} 不允许 fallback (allow_auto_fallback=False)")

        # 2. manual 模式: 直接返回锁定模型
        if mode == "manual" and not force_fallback:
            return await self._select_manual(db, role_key, binding, role)

        # 3. manual_with_fallback: 先尝试主模型, 失败走 fallback
        if mode == "manual_with_fallback" and not force_fallback:
            primary_ok = await self._check_primary_available(db, binding)
            if primary_ok:
                return await self._select_manual(db, role_key, binding, role)

        # 4. auto / fallback: 按评分选最佳
        profile = AGENT_CAPABILITY_PROFILE.get(role_key, {})
        candidates = await self._score_all_candidates(db, binding, profile, strategy, role_key)

        if not candidates:
            # 最后兜底: 任何 enabled provider
            return await self._fallback_any_enabled(db, role_key, role)

        best = candidates[0]

        # 5. 构建 SelectedModel
        provider = await db.get(ModelProvider, best.provider_id)
        if provider is None:
            raise ValueError(f"Provider {best.provider_id} 不存在")

        return SelectedModel(
            provider=provider,
            model_name=best.model_name,
            temperature=best.temperature or (binding.temperature if binding else None) or 0.7,
            max_tokens=best.max_tokens or (binding.max_tokens if binding else None) or 2048,
            extra_body=best.extra_body or (binding.extra_body if binding else None),
            selection_mode=mode,
            selection_score=best.score,
            selection_reason=best.reason,
            candidates=candidates,
        )

    # ── 内部方法 ──

    async def _get_role_and_binding(
        self, db: AsyncSession, role_key: str,
    ) -> tuple[AgentRole | None, AgentModelBinding | None]:
        role = (await db.execute(
            select(AgentRole).where(AgentRole.key == role_key)
        )).scalar_one_or_none()
        if role is None:
            return None, None
        binding = (await db.execute(
            select(AgentModelBinding).where(AgentModelBinding.agent_role_id == role.id)
        )).scalar_one_or_none()
        return role, binding

    async def _select_manual(
        self, db: AsyncSession, role_key: str,
        binding: AgentModelBinding, role: AgentRole | None,
    ) -> SelectedModel:
        if not binding or not binding.provider_id:
            raise ValueError(f"Agent {role_key} 手动模式但未绑定 Provider")
        provider = await db.get(ModelProvider, binding.provider_id)
        if provider is None:
            raise ValueError(f"Provider {binding.provider_id} 不存在")
        model = binding.model_name or provider.default_model or "unknown"
        if not is_text_role_model_compatible(role_key, model):
            raise ValueError(
                f"Agent {role_key} is bound to media model {model}; text agents require a chat/text model"
            )
        return SelectedModel(
            provider=provider,
            model_name=model,
            temperature=binding.temperature or 0.7,
            max_tokens=binding.max_tokens or 2048,
            extra_body=binding.extra_body,
            selection_mode="manual",
            selection_score=0.0,
            selection_reason=f"手动锁定: {provider.name}/{model}",
            candidates=[],
        )

    async def _check_primary_available(
        self, db: AsyncSession, binding: AgentModelBinding,
    ) -> bool:
        if not binding.provider_id:
            return False
        provider = await db.get(ModelProvider, binding.provider_id)
        if provider is None or not provider.enabled:
            return False
        if provider.circuit_state == "open":
            if provider.circuit_open_until and provider.circuit_open_until > datetime.utcnow():
                return False
        model = binding.model_name or provider.default_model or ""
        if model and not is_text_role_model_compatible("", model):
            return False
        return True

    async def _score_all_candidates(
        self,
        db: AsyncSession,
        binding: AgentModelBinding | None,
        profile: dict,
        strategy: str,
        role_key: str,
    ) -> list[ModelCandidate]:
        """对所有可用 Provider+Model 评分排序."""
        weights = STRATEGY_WEIGHTS.get(strategy, STRATEGY_WEIGHTS["quality_first"])

        # 确定候选 provider 池
        allowed_provider_ids = None
        if binding and binding.candidate_provider_ids:
            allowed_provider_ids = binding.candidate_provider_ids

        # 查询可用 Provider
        q = select(ModelProvider).where(ModelProvider.enabled == True)  # noqa: E712
        if allowed_provider_ids:
            q = q.where(ModelProvider.id.in_(allowed_provider_ids))
        providers = (await db.execute(q)).scalars().all()

        # 确定候选模型列表
        explicit_models: list[dict] = []
        if binding and binding.candidate_models_json:
            explicit_models = binding.candidate_models_json

        # fallback 候选
        fallback_models: list[dict] = []
        if binding and binding.fallback_candidates_json:
            fallback_models = binding.fallback_candidates_json

        candidates: list[ModelCandidate] = []

        for p in providers:
            if provider_priority_score(p) < 0.5:
                continue
            health = provider_health_score(p)
            if _should_skip_open_provider(p):
                # 完全熔断, 跳过
                if not (p.circuit_open_until and p.circuit_open_until <= datetime.utcnow()):
                    continue

            # 确定该 Provider 下的模型列表
            models_to_score: list[str] = []

            if explicit_models:
                # 只评分显式指定的模型
                for m in explicit_models:
                    if m.get("provider_id") == p.id:
                        models_to_score.append(m["model"])
            else:
                # 用 Provider 的 model_list
                models_to_score = list(p.model_list or [])
                if p.default_model and p.default_model not in models_to_score:
                    models_to_score.insert(0, p.default_model)

            for model_name in models_to_score:
                if not is_text_role_model_compatible(role_key, model_name):
                    continue
                if await _recent_model_failure(db, p.id, model_name):
                    continue
                # 获取运行统计
                stat = (await db.execute(
                    select(ModelRuntimeStat).where(
                        and_(
                            ModelRuntimeStat.provider_id == p.id,
                            ModelRuntimeStat.model_name == model_name,
                            ModelRuntimeStat.agent_role_key == role_key,
                            ModelRuntimeStat.window == "rolling_24h",
                        )
                    )
                )).scalar_one_or_none()
                if not _usable_runtime_stat(stat):
                    stat = None

                # 计算各项分数
                cap = capability_match(profile, p, model_name, stat)
                hlth = health
                succ = _clamp(stat.success_calls / max(stat.total_calls, 1)) if stat else 0.8
                lat = latency_score(stat.avg_latency_ms if stat else p.avg_latency_ms)
                cst = cost_score(model_name)
                api = provider_priority_score(p)
                power = model_power_score(model_name)
                quality_need = role_quality_need(profile, role_key)
                role_fit = _clamp(power * quality_need + cst * (1 - quality_need))
                modality_penalty = text_role_modality_penalty(role_key, model_name)
                jsn = json_stability_score(stat)
                ctx = 0.7  # 简化: 暂不区分上下文长度

                # 风险检查
                risks: list[str] = []
                if api <= 0.0:
                    risks.append("mock/provider 仅作兜底")
                elif api < 0.5:
                    risks.append("本地 provider 低优先级")
                if quality_need >= 0.75 and power < 0.55:
                    risks.append("小模型不适合高质量角色")
                if p.circuit_state == "half_open":
                    risks.append("熔断恢复探测中")
                if p.consecutive_failures >= 2:
                    risks.append(f"连续失败{p.consecutive_failures}次")
                if stat and stat.json_parse_failures > 3 and profile.get("needs_json"):
                    risks.append(f"JSON解析失败{stat.json_parse_failures}次")
                if modality_penalty:
                    risks.append("多媒体专用模型不适合文本角色")
                risk_penalty = len(risks) * 0.05 + modality_penalty

                # 综合评分
                base_score = (
                    cap * weights.get("capability", 0.30)
                    + hlth * weights.get("health", 0.25)
                    + succ * weights.get("success", 0.18)
                    + lat * weights.get("latency", 0.10)
                    + cst * weights.get("cost", 0.08)
                    + jsn * weights.get("json", 0.06)
                    + ctx * weights.get("context", 0.03)
                )
                score = (
                    base_score * 0.78
                    + api * 0.12
                    + role_fit * 0.10
                    - risk_penalty
                )
                score = _clamp(score, 0, 1)

                reason_parts = []
                if api >= 0.9:
                    reason_parts.append("真实API优先")
                elif api < 0.5:
                    reason_parts.append("本地/Mock降权")
                if modality_penalty:
                    reason_parts.append("多媒体模型不适合文本角色")
                if quality_need >= 0.75 and power >= 0.75:
                    reason_parts.append("高质量角色匹配大模型")
                if quality_need < 0.5 and cst > 0.8:
                    reason_parts.append("低风险角色匹配小模型")
                if hlth < 0.5:
                    reason_parts.append(f"健康分低({hlth:.0%})")
                if succ < 0.9:
                    reason_parts.append(f"成功率{succ:.0%}")
                if lat > 0.8:
                    reason_parts.append("延迟低")
                if cst > 0.8:
                    reason_parts.append("成本低")
                reason = ", ".join(reason_parts) if reason_parts else "综合评分最优"

                candidates.append(ModelCandidate(
                    provider_id=p.id,
                    provider_name=p.name,
                    base_url=p.base_url,
                    api_key=p.api_key,
                    model_name=model_name,
                    score=score,
                    reason=reason,
                    temperature=binding.temperature if binding else None,
                    max_tokens=binding.max_tokens if binding else None,
                    extra_body=binding.extra_body if binding else None,
                    health=hlth,
                    success_rate=succ,
                    latency_ms=stat.avg_latency_ms if stat else p.avg_latency_ms,
                    cost_score=cst,
                    risk=risks,
                ))

        # 也加入 fallback 候选 (如果不在候选池中)
        for fb in fallback_models:
            pid = fb.get("provider_id")
            mname = fb.get("model")
            if pid and mname and not any(
                c.provider_id == pid and c.model_name == mname for c in candidates
            ):
                if not is_text_role_model_compatible(role_key, mname):
                    continue
                if await _recent_model_failure(db, pid, mname):
                    continue
                fp = await db.get(ModelProvider, pid)
                if fp and fp.enabled:
                    # 计算真实评分，而非固定 0.1
                    # fallback 候选本质上是"主候选之外的保险"，其分数上限比主候选
                    # 低一档（乘以 0.75 衰减系数），确保正常候选优先被选中。
                    fb_hlth = provider_health_score(fp)
                    fb_stat = (await db.execute(
                        select(ModelRuntimeStat).where(
                            and_(
                                ModelRuntimeStat.provider_id == fp.id,
                                ModelRuntimeStat.model_name == mname,
                                ModelRuntimeStat.agent_role_key == role_key,
                                ModelRuntimeStat.window == "rolling_24h",
                            )
                        )
                    )).scalar_one_or_none()
                    if not _usable_runtime_stat(fb_stat):
                        fb_stat = None
                    fb_succ = _clamp(fb_stat.success_calls / max(fb_stat.total_calls, 1)) if fb_stat else 0.7
                    fb_lat = latency_score(fb_stat.avg_latency_ms if fb_stat else fp.avg_latency_ms)
                    fb_cst = cost_score(mname)
                    fb_jsn = json_stability_score(fb_stat)
                    fb_modality_penalty = text_role_modality_penalty(role_key, mname)
                    fb_score = _clamp(
                        (
                            fb_hlth * weights.get("health", 0.25)
                            + fb_succ * weights.get("success", 0.18)
                            + fb_lat * weights.get("latency", 0.10)
                            + fb_cst * weights.get("cost", 0.08)
                            + fb_jsn * weights.get("json", 0.06)
                        ) * 0.75 - fb_modality_penalty,  # fallback 衰减系数，保证低于主候选
                        0.05, 0.65,
                    )
                    candidates.append(ModelCandidate(
                        provider_id=fp.id,
                        provider_name=fp.name,
                        base_url=fp.base_url,
                        api_key=fp.api_key,
                        model_name=mname,
                        score=fb_score,
                        reason=f"fallback候选(健康:{fb_hlth:.0%} 成功:{fb_succ:.0%})",
                        health=fb_hlth,
                        success_rate=fb_succ,
                        latency_ms=fb_stat.avg_latency_ms if fb_stat else fp.avg_latency_ms,
                        cost_score=fb_cst,
                        risk=(["多媒体专用模型不适合文本角色"] if fb_modality_penalty else []),
                    ))

        # 按分数降序排列
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates

    async def _fallback_any_enabled(
        self, db: AsyncSession, role_key: str, role: AgentRole | None,
    ) -> SelectedModel:
        """最终兜底: 选第一个 enabled 的真实 Provider."""
        providers = (await db.execute(
            select(ModelProvider).where(
                and_(
                    ModelProvider.enabled == True,  # noqa: E712
                    ModelProvider.base_url != "mock://",
                )
            )
        )).scalars().all()

        providers = sorted(providers, key=provider_priority_score, reverse=True)
        for provider in providers:
            if provider_priority_score(provider) < 0.5:
                continue
            if _should_skip_open_provider(provider):
                continue
            models = list(provider.model_list or [])
            if provider.default_model and provider.default_model not in models:
                models.insert(0, provider.default_model)
            model = None
            for candidate in models:
                if not is_text_role_model_compatible(role_key, candidate):
                    continue
                if await _recent_model_failure(db, provider.id, candidate):
                    continue
                model = candidate
                break
            if not model:
                continue
            return SelectedModel(
                provider=provider,
                model_name=model,
                temperature=0.7,
                max_tokens=2048,
                extra_body=None,
                selection_mode="auto",
                selection_score=0.0,
                selection_reason=f"Fallback selected: {provider.name}/{model}",
                candidates=[],
            )

        raise ValueError(f"Agent {role_key} has no compatible text provider/model")



# ── 单例 ──────────────────────────────────────────────

_model_selector: ModelSelectorService | None = None


def get_model_selector() -> ModelSelectorService:
    global _model_selector
    if _model_selector is None:
        _model_selector = ModelSelectorService()
    return _model_selector
