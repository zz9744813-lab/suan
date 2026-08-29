"""每日预测闭环编排。

对应工程方案：
- 第 2.1 节 每日闭环
- 第 3 节 系统主动预测（系统不等待用户提问）
- 第 12 节 Blind Multi-Agent
- 第 21 节 对抗性 Gate
- 第 58 节 Scheduler

    23:30 更新 Reality State
    23:40 Future Scanner
    23:45 术数计算
    23:50 多 Agent + 对抗审查
    23:55 Freeze tomorrow predictions
    次日晚 Outcome verification

第 12 节核心约束：
    各术式 Agent 独立计算，提交 Fusion 前互不知晓彼此结论。
    本管线在结构上保证这点：每个 Adapter/Agent 只接收自己的输入。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlmodel import Session

from app.agents.base import AgentContext
from app.agents.fusion import fuse, FusionInput
from app.agents.pipeline_agents import (
    CandidateAgent,
    FreezeAgent,
    FutureScannerAgent,
)
from app.agents.registry import BaziAgent, NullAgent, RealityAgent, ZiweiAgent
from app.adversarial.attacks.base import AttackContext
from app.adversarial.gate import AdversarialGate
from app.config import get_settings
from app.core.base import AdapterQuery
from app.core.calendar.core import CalendarCore
from app.models.prediction import ForecastCandidate, PredictionFreeze, PredictionRecord
from app.models.reality import DailyState
from app.prediction.budget import apply_budget, default_slots
from app.prediction.ontology import ONTOLOGY, by_scale
from app.reality.null_model import NullModel
from app.reality.state import build_reality_state, persist_daily_state
from app.schemas.prediction import Prediction, PredictionCandidate
from app.schemas.signal import Domain, Signal, TimeScale, TimeWindow

logger = logging.getLogger(__name__)

SCALE_BY_NAME = {
    "day": TimeScale.DAY,
    "week": TimeScale.WEEK,
    "month": TimeScale.MONTH,
    "year": TimeScale.YEAR,
}


@dataclass
class PipelineResult:
    """一次管线运行的产物。"""

    target_date: date
    scanned: int = 0
    candidates: list[PredictionCandidate] = field(default_factory=list)
    frozen: list[Prediction] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    budget_usage: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_date": self.target_date.isoformat(),
            "scanned": self.scanned,
            "candidate_count": len(self.candidates),
            "frozen": [
                {
                    "prediction_id": p.prediction_id,
                    "event_type": p.event_type,
                    "probability": p.probability,
                    "null_probability": p.null_probability,
                    "sha256": (p.prediction_hash or "")[:16],
                    "visibility": p.visibility_mode.value,
                }
                for p in self.frozen
            ],
            "rejected": self.rejected,
            "budget_usage": self.budget_usage,
            "notes": self.notes,
        }


class DailyPipeline:
    """每日预测闭环。"""

    def __init__(self, session: Session, user_id: int) -> None:
        self.session = session
        self.user_id = user_id
        self.settings = get_settings()
        # 第 34 节双盲实验：None=正常融合；reality_null / metaphysical_only / fusion
        self.experiment_arm: str | None = None

    # ==================================================================
    # 23:30 更新 Reality State
    # ==================================================================
    def update_reality_state(self, target_date: date | None = None) -> DailyState:
        return persist_daily_state(
            self.session, user_id=self.user_id, target_date=target_date
        )

    # ==================================================================
    # 23:40 Future Scanner
    # ==================================================================
    def scan(self, target_date: date, scale: str = "day", limit: int = 50) -> list[dict[str, Any]]:
        state = build_reality_state(self.session, user_id=self.user_id, target_date=target_date)
        ctx = AgentContext(
            user_id=self.user_id,
            session=self.session,
            payload={"time_scale": scale, "target_date": target_date.isoformat(), "reality_state": state},
        )
        return FutureScannerAgent().scan(ctx, limit=limit)

    # ==================================================================
    # 23:45 术数计算 + 23:50 多 Agent + 对抗审查 → 23:55 Freeze
    # ==================================================================
    def run(
        self,
        target_date: date | None = None,
        scale: str = "day",
        limit: int = 20,
    ) -> PipelineResult:
        target_date = target_date or (date.today() + timedelta(days=1))
        time_scale = SCALE_BY_NAME.get(scale, TimeScale.DAY)
        result = PipelineResult(target_date=target_date)

        # ---------- 1. Reality State ----------
        self.update_reality_state(target_date)
        reality_state = build_reality_state(
            self.session, user_id=self.user_id, target_date=target_date
        )

        # ---------- 2. Scan ----------
        scanned = self.scan(target_date, scale=scale, limit=limit)
        result.scanned = len(scanned)
        if not scanned:
            result.notes.append("Future Scanner 未产出候选")
            return result

        window = FreezeAgent.default_window(
            datetime(target_date.year, target_date.month, target_date.day), time_scale
        )

        # ---------- 3. 逐候选：Blind Agents ----------
        for item in scanned:
            event_type = item.get("event_type", "")
            spec = ONTOLOGY.get(event_type)
            domain = _domain(item.get("domain", "") or (spec.domain if spec else ""))

            try:
                signals, null_p = self._collect_signals(
                    event_type=event_type,
                    domain=domain,
                    window=window,
                    time_scale=time_scale,
                    target_date=target_date,
                    reality_state=reality_state,
                    experiment_arm=self.experiment_arm,
                )
            except Exception as exc:
                result.notes.append(f"{event_type} 信号收集失败：{exc}")
                continue

            # ---------- 4. Fusion（第 12 节：只消费结构化 Signal）----------
            fusion = fuse(
                FusionInput(
                    signals=signals,
                    null_probability=null_p,
                    time_scale=time_scale,
                    reliability=self._reliability_weights(),
                )
            )

            # ---------- 5. CandidateAgent → 可验证预测 ----------
            cand = self._build_candidate(
                event_type=event_type,
                domain=domain,
                window=window,
                time_scale=time_scale,
                reality_state=reality_state,
                probability=fusion.probability,
                null_probability=null_p,
                signals=signals,
            )
            if cand is None:
                result.notes.append(f"{event_type} 无法构造可证伪候选（C-001）")
                continue

            # ---------- 6. Adversarial Gate（第 21 节）----------
            gate_result = AdversarialGate().run(
                self._attack_context(cand, null_p, fusion, len(scanned))
            )
            if gate_result.decision in {"REJECT", "REWRITE"}:
                result.rejected.append(
                    {
                        "event_type": event_type,
                        "decision": gate_result.decision,
                        "failed": [o.attack for o in gate_result.failed],
                        "reasons": [o.reason for o in gate_result.failed][:3],
                    }
                )
                continue

            result.candidates.append(cand)

        # ---------- 7. Prediction Budget（第 4 节）----------
        selected, usage = apply_budget(result.candidates, default_slots(self.settings))
        result.budget_usage = usage
        result.notes.append(
            f"预算竞争：{len(result.candidates)} 候选 → {len(selected)} 条获得额度"
        )

        # ---------- 8. Freeze（第 16 节）----------
        for cand in selected:
            pred = self._freeze(cand, fusion=None)
            if pred:
                result.frozen.append(pred)

        return result

    # ==================================================================
    def _collect_signals(
        self,
        *,
        event_type: str,
        domain: Domain,
        window: TimeWindow,
        time_scale: TimeScale,
        target_date: date,
        reality_state: dict[str, Any],
        experiment_arm: str | None = None,
    ) -> tuple[list[Signal], float]:
        """Blind 收集各源信号。

        第 12 节：每个 Adapter/Agent 只拿到自己的输入，
        不存在任何 agent 读取他人结论的路径。

        第 34 节双盲实验（arm）：
            reality_null      → 只用 Reality + Null（排除术数）
            metaphysical_only → 只用术式 + Null（排除 Reality）
            fusion / None     → 全部信号
        """
        signals: list[Signal] = []

        # --- Null Model（第 11 节，所有 arm 都必须提供基线）---
        null_model = NullModel(self.session)
        null_signal = null_model.signal(
            user_id=self.user_id,
            event_type=event_type,
            domain=domain,
            window=window,
            time_scale=time_scale,
        )
        null_p = null_signal.strength
        signals.append(null_signal)

        # --- Reality（第 10 节）---
        # 无现实事件时跳过 LLM 调用（纯 Null 基线即可），
        # 减少免费模型池的调用量与延迟。
        if experiment_arm != "metaphysical_only":
            try:
                total_events = reality_state.get("_meta", {}).get("total_events", 0)
                if total_events > 0:
                    reality_ctx = AgentContext(
                        user_id=self.user_id,
                        session=self.session,
                        target_event=event_type,
                        domain=domain.value,
                        payload={
                            "window": window,
                            "time_scale": time_scale,
                            "reality_state": reality_state,
                            "engine_version": "reality-0.1.0",
                        },
                    )
                    r = RealityAgent().run(reality_ctx)
                    if r.ok:
                        sig = RealityAgent().to_signal(reality_ctx, r)
                        if not sig.degraded:
                            signals.append(sig)
            except Exception as exc:
                logger.warning("RealityAgent 失败：%s", exc)

        # --- 术式 Adapter（deterministic 部分，第 6.1 节）---
        query = AdapterQuery(
            user_id=self.user_id,
            domain=domain,
            target_event=event_type,
            time_scale=time_scale,
            window=window,
            target_date=target_date,
            session=self.session,
        )
        from app.core.base import registry as adapter_registry

        for adapter in adapter_registry.all():
            if not adapter.available:
                continue
            # 第 34 节双盲 A 组：只用 Reality + Null，排除全部术式
            if experiment_arm == "reality_null":
                continue
            try:
                signals.extend(adapter.signals(query))
            except Exception as exc:
                logger.warning("Adapter %s 失败：%s", adapter.source.value, exc)

        return signals, null_p

    # ------------------------------------------------------------------
    def _build_candidate(
        self,
        *,
        event_type: str,
        domain: Domain,
        window: TimeWindow,
        time_scale: TimeScale,
        reality_state: dict[str, Any],
        probability: float,
        null_probability: float,
        signals: list[Signal],
    ) -> PredictionCandidate | None:
        """CandidateAgent 生成可验证预测；LLM 不可用时回落 Ontology。"""
        spec = ONTOLOGY.get(event_type)

        ctx = AgentContext(
            user_id=self.user_id,
            session=self.session,
            target_event=event_type,
            domain=domain.value,
            payload={
                "window": window,
                "window_text": f"{window.start.isoformat()} ~ {window.end.isoformat()}",
                "time_scale": time_scale,
                "null_probability": null_probability,
                "reality_state": reality_state,
            },
        )

        cand = CandidateAgent().build_candidate(
            ctx, window=window, time_scale=time_scale, signals=signals
        )

        if cand is not None:
            return cand

        # 回落：直接用 Ontology 定义（第 56 节），保证可证伪
        if spec is None:
            return None
        return PredictionCandidate(
            domain=domain,
            event_type=event_type,
            description=f"{spec.label}（{spec.event_type}）",
            probability=probability,
            time_scale=time_scale,
            window_start=window.start,
            window_end=window.end,
            success_criteria=list(spec.success_criteria),
            failure_criteria=list(spec.failure_criteria),
            grading_rule=spec.grading_rule,
            signals=signals,
        )

    # ------------------------------------------------------------------
    def _attack_context(
        self,
        cand: PredictionCandidate,
        null_p: float,
        fusion: Any,
        pool_size: int,
    ) -> AttackContext:
        """构造 Gate 输入。

        第 20.12 节：把 dependency_group 传给 CorrelatedEvidenceAttack。
        """
        groups: dict[str, list[str]] = {}
        for s in cand.signals:
            key = s.dependency_group or f"solo:{s.source.value}"
            groups.setdefault(key, []).append(s.source.value)

        return AttackContext(
            description=cand.description,
            event_type=cand.event_type,
            probability=cand.probability,
            null_probability=null_p,
            success_criteria=cand.success_criteria,
            failure_criteria=cand.failure_criteria,
            window_start=cand.window_start,
            window_end=cand.window_end,
            grading_rule=cand.grading_rule,
            signals=[s.model_dump(mode="json") for s in cand.signals],
            dependency_groups=groups,
            candidate_pool_size=pool_size,
        )

    # ------------------------------------------------------------------
    def _reliability_weights(self) -> dict[str, float]:
        """第 26 节：从历史 skill 学习到的融合权重。样本不足时为 {}（即 1.0）。"""
        try:
            from app.learning.reliability import ReliabilityMatrix

            return ReliabilityMatrix(self.session, user_id=self.user_id).fusion_weights()
        except Exception:
            return {}

    # ------------------------------------------------------------------
    def _freeze(self, cand: PredictionCandidate, fusion: Any = None) -> Prediction | None:
        """第 16 节：预注册 + 冻结 + 落库。"""
        visibility = "HIDDEN" if self.settings.EXPERIMENT_MODE == "hidden" else "VISIBLE"

        pred = Prediction(
            user_id=str(self.user_id),
            domain=cand.domain,
            event_type=cand.event_type,
            description=cand.description,
            probability=cand.probability,
            window_start=cand.window_start,
            window_end=cand.window_end,
            time_scale=cand.time_scale,
            success_criteria=cand.success_criteria,
            failure_criteria=cand.failure_criteria,
            grading_rule=cand.grading_rule,
            null_probability=next(
                (s.strength for s in cand.signals if s.source.value == "null"), None
            ),
            visibility_mode=visibility,  # type: ignore[arg-type]
            candidate_id=cand.candidate_id,
            signals=cand.signals,
            input_snapshot={
                "signal_count": len(cand.signals),
                # 必须是 list：set 无法 JSON 序列化，落库会报 StatementError
                "dependency_groups": sorted(
                    {s.dependency_group or f"solo:{s.source.value}" for s in cand.signals}
                    - {""}
                ),
                "signal_sources": [s.source.value for s in cand.signals],
            },
        )

        ctx = AgentContext(
            user_id=self.user_id,
            session=self.session,
            payload={"prediction": pred},
        )
        out = FreezeAgent().run(ctx)
        if not out.ok:
            return None

        # 落库：predictions
        record = PredictionRecord(
            prediction_id=pred.prediction_id,
            user_id=self.user_id,
            domain=pred.domain.value,
            event_type=pred.event_type,
            description=pred.description,
            probability=pred.probability,
            null_probability=pred.null_probability,
            time_scale=pred.time_scale.value,
            window_start=pred.window_start,
            window_end=pred.window_end,
            success_criteria=pred.success_criteria,
            failure_criteria=pred.failure_criteria,
            grading_rule=pred.grading_rule,
            status=pred.status.value,
            visibility_mode=pred.visibility_mode.value,
            created_at=pred.created_at,
            frozen_at=pred.frozen_at,
            verification_due_at=pred.verification_due_at,
            sha256=pred.prediction_hash,
            model_version=pred.model_version,
            fusion_version=pred.fusion_version,
            prompt_version=pred.prompt_version,
            rule_version=pred.rule_version,
            engine_version=pred.engine_version,
            candidate_id=pred.candidate_id,
            version=pred.version,
        )
        self.session.add(record)

        # 落库：signals
        from app.models.prediction import SignalRecord

        for s in pred.signals:
            self.session.add(
                SignalRecord(
                    signal_id=s.signal_id,
                    prediction_id=pred.prediction_id,
                    prediction_candidate_id=cand.candidate_id,
                    source_type=s.source.value,
                    source_engine=s.engine_version,
                    domain=s.domain.value,
                    target_event=s.target_event,
                    direction=s.direction,
                    strength=s.strength,
                    confidence=s.confidence,
                    time_scale=s.time_scale.value,
                    window_start=s.time_window.start,
                    window_end=s.time_window.end,
                    evidence=[e.model_dump(mode="json") for e in s.evidence],
                    counter_evidence=[e.model_dump(mode="json") for e in s.counter_evidence],
                    rule_ids=s.rule_ids,
                    dependency_group=s.dependency_group,
                    engine_version=s.engine_version,
                    prompt_version=s.prompt_version,
                    degraded=s.degraded,
                    degrade_reason=s.degrade_reason,
                )
            )

        # 落库：freeze 快照（第 16 节）
        self.session.add(
            PredictionFreeze(
                prediction_id=pred.prediction_id,
                freeze_payload=pred.freeze_payload(),
                agent_outputs=[],
                input_snapshot=pred.input_snapshot or {},
                sha256=pred.prediction_hash or "",
                frozen_at=pred.frozen_at or datetime.utcnow(),
            )
        )
        self.session.commit()
        return pred


# ----------------------------------------------------------------------
def _domain(value: str) -> Domain:
    try:
        return Domain(value)
    except ValueError:
        return Domain.UNEXPECTED_EVENT
