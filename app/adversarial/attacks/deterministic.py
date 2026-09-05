"""14 种对抗性攻击的确定性实现。

对应工程方案第 20.1 - 20.14 节。

全部不依赖 LLM —— 对抗性审查是系统的最后防线，
它本身不能再依赖一个会产生幻觉的组件。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .base import Attack, AttackContext, AttackOutcome, Verdict


# ======================================================================
# 20.1 VaguenessAttack
# ======================================================================
class VaguenessAttack(Attack):
    """预测是否模糊到怎么解释都成立？

    第 20.1 节示例：「明天可能有变化。」→ 直接 Reject。
    """

    name = "VaguenessAttack"

    VAGUE_TERMS = [
        "可能", "也许", "或许", "大概", "似乎", "感觉", "某种", "一些",
        "变化", "机遇", "机会", "注意", "留意", "相关", "影响", "潜在",
        "倾向", "或许会", "说不定", "看情况", "有待", "有望",
    ]
    MIN_DESCRIPTION_LEN = 12

    def run(self, ctx: AttackContext) -> AttackOutcome:
        text = ctx.description or ""
        if not text:
            return self._fail("描述为空，无法判定是否发生（C-001）")

        hits = [t for t in self.VAGUE_TERMS if t in text]
        hit_ratio = len(hits) / max(1, len(text))

        # 短描述 + 模糊词 = 必然模糊
        if len(text) < self.MIN_DESCRIPTION_LEN and hits:
            return self._fail(
                f"描述过短且含模糊词 {hits}，几乎任何结果都能解释为命中",
                details={"hits": hits, "length": len(text)},
            )

        if hit_ratio > 0.08:
            return self._fail(
                f"模糊词密度过高（{hit_ratio:.1%}）：{hits[:5]}",
                severity=min(1.0, hit_ratio * 5),
                details={"hits": hits},
            )

        if hits:
            return self._warn(f"含模糊词：{hits}", severity=0.3, details={"hits": hits})

        return self._pass("描述具体")


# ======================================================================
# 20.2 BarnumAttack
# ======================================================================
class BarnumAttack(Attack):
    """判断是否属于「大多数人、大多数日子都成立」。

    第 20.2 节示例：「你今天可能有些情绪波动。」→ Reject / 降权。
    """

    name = "BarnumAttack"
    blocking = False  # 降权而非直接拒绝

    BARNUM_PATTERNS = [
        r"你(有时|偶尔|常常|有时候)",
        r"你(希望|渴望|需要)",
        r"你外表",
        r"你(其实|内心)",
        r"情绪(波动|起伏|变化)",
        r"人际(关系|交往)",
        r"需要(注意|留意)身体",
        r"压力(较大|有点)",
        r"会有(贵人|机遇|转机)",
        r"运势(上升|好转|不错)",
        r"小心(小人|口舌)",
    ]

    def run(self, ctx: AttackContext) -> AttackOutcome:
        text = f"{ctx.description} {' '.join(ctx.success_criteria)}"
        if not text.strip():
            return self._skip()

        hits = [p for p in self.BARNUM_PATTERNS if re.search(p, text)]
        if hits:
            return self._warn(
                f"命中巴纳姆式陈述 {len(hits)} 条：这类描述对大多数人都成立",
                severity=min(1.0, 0.4 + 0.2 * len(hits)),
                details={"matched": hits[:5]},
            )
        return self._pass("非巴纳姆式陈述")


# ======================================================================
# 20.3 DefinitionAttack
# ======================================================================
class DefinitionAttack(Attack):
    """攻击定义。

    第 20.3 节：
        例如「会遇到贵人。」
        系统必须问：贵人是什么？怎样记录？怎样判断没有遇到？
        无法定义则 Reject。
    """

    name = "DefinitionAttack"

    UNDEFINABLE_TERMS = ["贵人", "小人", "桃花", "运势", "气场", "能量", "福报", "机缘"]
    VAGUE_IN_CRITERIA = ["可能", "也许", "大概", "相关", "差不多", "某种程度"]

    def run(self, ctx: AttackContext) -> AttackOutcome:
        if not ctx.success_criteria:
            return self._fail("缺少成功标准，无法判定「发生」（C-001 可证伪原则）")
        if not ctx.failure_criteria:
            return self._fail(
                "缺少失败标准 —— 无法判定「没有遇到」，预测不可证伪（第 20.3 节）"
            )

        all_text = (
            ctx.description
            + " "
            + " ".join(ctx.success_criteria + ctx.failure_criteria)
            + " "
            + (ctx.grading_rule or "")
        )

        undef = [t for t in self.UNDEFINABLE_TERMS if t in all_text]
        if undef:
            return self._fail(
                f"使用了无法观测的概念：{undef}。必须给出可记录的判定方式。",
                details={"terms": undef},
            )

        vague = [t for t in self.VAGUE_IN_CRITERIA if t in all_text]
        if vague:
            return self._fail(
                f"判定标准含模糊词：{vague}", severity=0.8, details={"terms": vague}
            )

        return self._pass("成功/失败标准明确且可观测")


# ======================================================================
# 20.4 TimeWindowAttack
# ======================================================================
class TimeWindowAttack(Attack):
    """必须具有明确时间窗口。

    第 20.4 节：「未来可能……」→ Reject。
    """

    name = "TimeWindowAttack"

    MAX_WINDOW_DAYS = 400

    def run(self, ctx: AttackContext) -> AttackOutcome:
        if ctx.window_start is None or ctx.window_end is None:
            return self._fail("缺少明确时间窗口（第 20.4 节）")

        try:
            start, end = _as_dt(ctx.window_start), _as_dt(ctx.window_end)
        except (TypeError, ValueError):
            return self._fail("时间窗口格式无法解析")

        if end <= start:
            return self._fail(f"时间窗口非法：end({end}) 不晚于 start({start})")

        days = (end - start).days
        if days > self.MAX_WINDOW_DAYS:
            return self._warn(
                f"时间窗口过长（{days} 天），可证伪性下降",
                severity=min(1.0, days / 1000),
                details={"days": days},
            )

        return self._pass(f"窗口明确（{days} 天）", days=days)


# ======================================================================
# 20.5 CherryPickAttack
# ======================================================================
class CherryPickAttack(Attack):
    """检查是否只展示命中、隐藏失败。

    第 51 节：默认必须同时展示成功、失败、部分、无法判断。
    """

    name = "CherryPickAttack"
    blocking = False

    def run(self, ctx: AttackContext) -> AttackOutcome:
        if not ctx.input_snapshot:
            return self._skip("缺少输入快照")

        stats = ctx.input_snapshot.get("ledger_stats") or {}
        shown_hits = int(stats.get("shown_hits", 0))
        total = int(stats.get("total_verified", 0))

        if total == 0:
            return self._skip("尚无已验证样本")

        if shown_hits > total:
            return self._fail(
                f"展示的命中数({shown_hits}) 超过已验证总数({total})，存在选择性报告",
                details={"shown_hits": shown_hits, "total_verified": total},
            )

        hidden_failures = total - shown_hits
        if total >= 10 and shown_hits == total:
            return self._warn(
                "全部样本均展示为命中 —— 需核对是否隐藏了失败预测（第 51 节）",
                severity=0.6,
                details={"total": total},
            )

        return self._pass(f"命中 {shown_hits}/{total}，失败样本未隐藏")


# ======================================================================
# 20.6 MultipleTestingAttack
# ======================================================================
class MultipleTestingAttack(Attack):
    """统计候选/发布/命中。

    第 20.6 节：如果 Agent 每天产生大量预测，候选命中不得算作正式命中，
    只有冻结的 Prediction Ledger 才计分。
    """

    name = "MultipleTestingAttack"
    blocking = False

    # 候选转正式的比例上限：超过说明在撒网
    MAX_PUBLISH_RATIO = 0.2

    def run(self, ctx: AttackContext) -> AttackOutcome:
        if not ctx.candidate_pool_size:
            return self._skip("缺少候选池规模")

        published = ctx.published_count or 0
        pool = ctx.candidate_pool_size

        if pool <= 0:
            return self._skip()

        ratio = published / pool
        if ratio > self.MAX_PUBLISH_RATIO:
            return self._warn(
                f"候选转正式比例过高（{published}/{pool} = {ratio:.1%}），"
                f"疑似撒网式预测（第 4 节 Prediction Budget）",
                severity=min(1.0, ratio),
                details={"published": published, "pool": pool, "ratio": ratio},
            )

        return self._pass(f"发布比例正常（{published}/{pool}）", ratio=ratio)


# ======================================================================
# 20.7 RetrofittingAttack
# ======================================================================
class RetrofittingAttack(Attack):
    """检查结果产生以后是否修改了预测原文。

    第 16 节：冻结后 UPDATE 原文 = 禁止。
    """

    name = "RetrofittingAttack"

    def run(self, ctx: AttackContext) -> AttackOutcome:
        if not ctx.prediction_hash:
            return self._skip("预测尚未冻结")

        if ctx.recomputed_hash is None:
            return self._skip("未提供重算哈希，无法校验")

        if ctx.prediction_hash != ctx.recomputed_hash:
            return self._fail(
                "预测原文已被修改（哈希不匹配）—— 判为事后改装，一律记失败",
                details={
                    "stored": ctx.prediction_hash[:16],
                    "recomputed": ctx.recomputed_hash[:16],
                },
            )

        if ctx.window_started:
            # 第 59 节：窗口已开始仍被编辑
            return self._fail("预测窗口已开始，预测内容却发生变更")

        return self._pass("原文完整，未被事后修改")


# ======================================================================
# 20.8 OutcomeLeakAttack
# ======================================================================
class OutcomeLeakAttack(Attack):
    """检查预测生成时是否已经包含结果信息。

    第 20.8 节：日记已记录 / 日历已确定 / 用户已告知 / 网络数据已显示结果。
    有泄漏 → LEAKED，不进入预测评分。
    """

    name = "OutcomeLeakAttack"

    LEAK_KEYS = ["outcome_known", "already_happened", "result_visible", "leaked"]

    def run(self, ctx: AttackContext) -> AttackOutcome:
        snapshot = ctx.input_snapshot or {}

        for k in self.LEAK_KEYS:
            if snapshot.get(k):
                return self._fail(f"输入快照标记为 {k}，预测已含结果信息")

        # 时间维度：预测创建于窗口结束之后 = 必然泄漏
        if ctx.created_at is not None and ctx.window_end is not None:
            try:
                created, end = _as_dt(ctx.created_at), _as_dt(ctx.window_end)
                if created > end:
                    return self._fail(
                        f"预测创建时间({created}) 晚于窗口结束({end})—— 结果已知",
                        details={"created": str(created), "window_end": str(end)},
                    )
            except (TypeError, ValueError):
                pass

        return self._pass("未检出结果泄漏")


# ======================================================================
# 20.9 SelfFulfillingAttack
# ======================================================================
class SelfFulfillingAttack(Attack):
    """第 20.9 节：系统预测「你今天会主动学习」→ 用户因预测才去学习。

    需要单独标记。第 35 节 Hidden Prediction Mode 是应对手段。
    """

    name = "SelfFulfillingAttack"
    blocking = False

    DEFAULT_FULFILLABLE = {
        "study.study_session",
        "habit.break",
        "money.unplanned_expense",
        "social.old_contact",
        "communication.message_volume_spike",
    }

    def run(self, ctx: AttackContext) -> AttackOutcome:
        fulfillable = ctx.self_fulfillable_event_types or self.DEFAULT_FULFILLABLE
        if ctx.event_type in fulfillable and ctx.visibility_mode == "VISIBLE":
            return self._warn(
                f"事件 {ctx.event_type} 易被预测本身影响，且当前对用户可见 —— "
                f"建议改用 Hidden Prediction Mode（第 35 节）",
                severity=0.6,
                details={"event_type": ctx.event_type, "visibility": ctx.visibility_mode},
            )
        return self._pass("自我实现风险低")


# ======================================================================
# 20.10 BaselineAttack
# ======================================================================
class BaselineAttack(Attack):
    """第 20.10 节：不使用术数，只用历史概率，会不会一样预测？

    必须和 Null Model 比。
    """

    name = "BaselineAttack"
    blocking = False

    # 与 Null 基线的差异阈值：低于此值说明没有增量信息
    MIN_DELTA = 0.03

    def run(self, ctx: AttackContext) -> AttackOutcome:
        if ctx.probability is None or ctx.null_probability is None:
            return self._skip("缺少 Null 基线概率，无法比较（第 11 节要求必须提供）")

        delta = abs(ctx.probability - ctx.null_probability)
        if delta < self.MIN_DELTA:
            return self._warn(
                f"与 Null 基线差异仅 {delta:.3f} —— 该预测几乎只是历史基础概率的复述，"
                f"信息价值低（第 20.10 节）",
                severity=0.5,
                details={"probability": ctx.probability, "null": ctx.null_probability},
            )
        return self._pass(f"相对 Null 基线有 {delta:.3f} 偏移", delta=delta)


# ======================================================================
# 20.11 AgentCollusionAttack
# ======================================================================
class AgentCollusionAttack(Attack):
    """第 20.11 节：检查不同 Agent 是否偷偷获得其他 Agent 输出。

    检测手段：
        1. agent_runs.saw_other_agents 标记
        2. 输出文本相似度（Jaccard）
        3. 是否由同一 Prompt 模板造成伪独立
    """

    name = "AgentCollusionAttack"

    SIMILARITY_THRESHOLD = 0.75

    def run(self, ctx: AttackContext) -> AttackOutcome:
        # 1. 框架层标记（最可靠）
        if any(ctx.agent_runs_saw_others):
            return self._fail(
                "存在 Agent 接触了其他 Agent 的输出，违反 Blind Multi-Agent（第 12 节）"
            )

        # 2. 文本相似度
        texts = {k: v for k, v in ctx.agent_texts.items() if v}
        if len(texts) < 2:
            return self._skip("Agent 输出不足，无法做相似度检测")

        names = list(texts)
        worst_pair, worst_sim = None, 0.0
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                sim = _jaccard(texts[names[i]], texts[names[j]])
                if sim > worst_sim:
                    worst_sim, worst_pair = sim, (names[i], names[j])

        if worst_pair and worst_sim > self.SIMILARITY_THRESHOLD:
            return self._fail(
                f"Agent {worst_pair[0]} 与 {worst_pair[1]} 输出相似度 {worst_sim:.2f}，"
                f"疑似相互锚定或共用模板（第 20.11 节）",
                severity=min(1.0, worst_sim),
                details={"pair": worst_pair, "similarity": worst_sim},
            )

        return self._pass(
            f"Agent 输出独立性正常（最高相似度 {worst_sim:.2f}）", similarity=worst_sim
        )


# ======================================================================
# 20.12 CorrelatedEvidenceAttack
# ======================================================================
class CorrelatedEvidenceAttack(Attack):
    """第 20.12 节：紫微、八字、黄历可能共享同类历法信号。

    不能因为「4 个术式支持」就错误理解成「4 个独立证据」。
    """

    name = "CorrelatedEvidenceAttack"
    blocking = False

    def run(self, ctx: AttackContext) -> AttackOutcome:
        groups = ctx.dependency_groups or {}
        # 找出「多源同组」：这些源并非独立
        correlated = {g: srcs for g, srcs in groups.items() if len(srcs) > 1}

        if not correlated:
            return self._pass("未发现相关证据组")

        total_sources = sum(len(s) for s in groups.values())
        effective = len(groups)  # 每组只算一份独立证据
        inflation = total_sources / max(1, effective)

        return self._warn(
            f"存在相关证据组 {list(correlated)}："
            f"{total_sources} 个源实际只提供 {effective} 份独立证据"
            f"（膨胀 {inflation:.1f}×）—— Fusion 已做去相关计权",
            severity=min(1.0, (inflation - 1) / 3),
            details={"correlated_groups": correlated, "inflation": inflation},
        )


# ======================================================================
# 20.13 ConfirmationBiasAttack
# ======================================================================
class ConfirmationBiasAttack(Attack):
    """第 20.13 节：检查 Outcome Judge 是否倾向把模糊现实描述判成「命中」。

    应同时运行 Prosecution / Defense / Neutral，分歧则 NEEDS_USER_CONFIRMATION。
    """

    name = "ConfirmationBiasAttack"
    blocking = False

    DISAGREEMENT_THRESHOLD = 0.5

    def run(self, ctx: AttackContext) -> AttackOutcome:
        verdicts = ctx.judge_verdicts or []
        if len(verdicts) < 2:
            return self._skip("不足两方 Judge，无法检测偏差")

        values = [float(v.get("outcome", 0.0)) for v in verdicts]
        disagreement = max(values) - min(values)

        if disagreement > self.DISAGREEMENT_THRESHOLD:
            return self._warn(
                f"三方 Judge 分歧达 {disagreement:.2f} —— 必须转人工确认，"
                f"不得强行判定（第 20.13 节）",
                severity=min(1.0, disagreement),
                details={"disagreement": disagreement, "verdicts": verdicts},
            )

        return self._pass(f"Judge 一致性良好（分歧 {disagreement:.2f}）")


# ======================================================================
# 20.14 NarrativeExcuseAttack
# ======================================================================
class NarrativeExcuseAttack(Attack):
    """第 20.14 节：禁止失败以后输出「只是应期延后」这类开脱。

    除非延迟窗口规则在预测冻结之前已注册，否则一律判失败。
    """

    name = "NarrativeExcuseAttack"

    EXCUSE_PATTERNS = [
        "应期延后", "应期未到", "延后应验", "推迟应验",
        "能量已经发生", "能量层面", "气场已经",
        "另一种形式应验", "以别的方式应验", "换了种形式",
        "这是潜在影响", "潜在层面", "隐性应验",
        "其实已经应了", "本质上是对的",
    ]

    def run(self, ctx: AttackContext) -> AttackOutcome:
        statements = ctx.post_hoc_statements or []
        if not statements:
            return self._skip("无事后陈述")

        hits = []
        for s in statements:
            for p in self.EXCUSE_PATTERNS:
                if p in s:
                    hits.append({"pattern": p, "statement": s[:80]})

        if hits:
            return self._fail(
                f"检出叙事性开脱 {len(hits)} 处 —— "
                f"除非延迟窗口规则在冻结前已注册，否则一律判失败（第 20.14 节）",
                details={"hits": hits[:5]},
            )

        return self._pass("无叙事性开脱")


# ======================================================================
# 注册表
# ======================================================================
ALL_ATTACKS: list[type[Attack]] = [
    VaguenessAttack,
    BarnumAttack,
    DefinitionAttack,
    TimeWindowAttack,
    OutcomeLeakAttack,
    CherryPickAttack,
    MultipleTestingAttack,
    RetrofittingAttack,
    SelfFulfillingAttack,
    BaselineAttack,
    AgentCollusionAttack,
    CorrelatedEvidenceAttack,
    ConfirmationBiasAttack,
    NarrativeExcuseAttack,
]


def build_attacks() -> list[Attack]:
    return [cls() for cls in ALL_ATTACKS]


# ----------------------------------------------------------------------
def _as_dt(v: Any) -> datetime:
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        return datetime.fromisoformat(v)
    raise TypeError(f"无法解析为 datetime：{type(v)}")


def _jaccard(a: str, b: str) -> float:
    """字符 3-gram Jaccard 相似度。"""
    def grams(s: str) -> set[str]:
        s = re.sub(r"\s+", "", s)
        return {s[i : i + 3] for i in range(max(0, len(s) - 2))}

    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


__all__ = [
    "ALL_ATTACKS",
    "build_attacks",
    "VaguenessAttack",
    "BarnumAttack",
    "DefinitionAttack",
    "TimeWindowAttack",
    "CherryPickAttack",
    "MultipleTestingAttack",
    "RetrofittingAttack",
    "OutcomeLeakAttack",
    "SelfFulfillingAttack",
    "BaselineAttack",
    "AgentCollusionAttack",
    "CorrelatedEvidenceAttack",
    "ConfirmationBiasAttack",
    "NarrativeExcuseAttack",
    "Verdict",
]
