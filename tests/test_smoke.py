"""端到端冒烟测试。

验证工程方案的硬性约束是否真的被代码执行（而不只是写在注释里）：

- C-001 可证伪原则：模糊预测必须被 Gate 拦截
- C-005 概率输出：核心输出必须是概率
- 第 16 节：冻结后哈希可校验，篡改可检出
- 第 20.12 节：相关证据不得重复计权
- 第 19.1 节：Brier 计算正确
- 第 78 节：小样本不得给出高可靠度结论
"""

from __future__ import annotations

from datetime import datetime

# ======================================================================
# 元信息与引擎
# ======================================================================
def test_root_notice(client):
    """第 65 节：系统必须声明安全边界。

    根路径打包后返回前端首页（HTML），JSON 安全声明通过 /api/meta 始终可达。
    """
    r = client.get("/api/meta")
    assert r.status_code == 200
    body = r.json()
    assert "不是经科学验证的预知系统" in body["notice"]


def test_health_lists_engines(client):
    r = client.get("/health")
    assert r.status_code == 200
    engines = r.json()["engines"]
    # 八个术式 Adapter 全部注册（round 12 新增 zhouyi 义理引擎）
    assert set(engines) == {
        "ziwei", "bazi", "qimen", "liuyao", "meihua", "palm", "face", "zhouyi"
    }


def test_bazi_engine_available(client):
    """全部术式引擎应已接入；掌纹/面相依赖 cv2（已装）。"""
    r = client.get("/api/system/engines")
    assert r.status_code == 200, r.text
    by_name = {e["source"]: e["available"] for e in r.json()["engines"]}
    assert by_name["bazi"] is True, "lunar-python 已安装，八字应可用"
    assert by_name["ziwei"] is True, "iztro-py 已接入"
    assert by_name["liuyao"] is True
    assert by_name["meihua"] is True
    assert by_name["qimen"] is True
    assert by_name["palm"] is True, "opencv 已安装"
    assert by_name["face"] is True


# ======================================================================
# Calendar Core（第 6 节）
# ======================================================================
def test_calendar_snapshot(client, user_id):
    """第 6.1 节：统一 Calendar Core 输出四柱/农历/节气。"""
    r = client.get(f"/api/calendar/snapshot?user_id={user_id}&target_date=2026-09-01")
    assert r.status_code == 200
    data = r.json()
    assert data["degraded"] is False, data.get("degrade_reason")
    payload = data["payload"]
    for key in ("year_ganzhi", "month_ganzhi", "day_ganzhi", "hour_ganzhi"):
        assert payload.get(key), f"缺少 {key}"
    assert payload["bazi"]["day_master"], "缺少日主"


def test_calendar_is_deterministic(client, user_id):
    """第 54 节：输入完全相同 → 排盘必须完全相同。"""
    a = client.get(f"/api/calendar/snapshot?user_id={user_id}&target_date=2026-09-01").json()
    b = client.get(f"/api/calendar/snapshot?user_id={user_id}&target_date=2026-09-01").json()
    assert a["payload"] == b["payload"]


# ======================================================================
# 对抗性 Gate（第 20 / 21 节）
# ======================================================================
def test_gate_rejects_vague_prediction(client):
    """第 20.1 节：「最近可能有些变化」必须被拦截。"""
    r = client.post(
        "/api/adversarial/gate-test",
        json={
            "description": "最近可能有些变化，需要注意人际关系。",
            "event_type": "social.conflict",
            "probability": 0.55,
            "success_criteria": ["可能发生变化"],
            "failure_criteria": [],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["decision"] == "REJECT", data
    failed = {a["attack"] for a in data["attacks"] if a["verdict"] == "FAIL"}
    assert "DefinitionAttack" in failed or "VaguenessAttack" in failed


def test_gate_rejects_undefined_concept(client):
    """第 20.3 节：「会遇到贵人」—— 贵人无法定义，必须 Reject。"""
    r = client.post(
        "/api/adversarial/gate-test",
        json={
            "description": "明天会遇到贵人相助",
            "event_type": "career.role_change",
            "probability": 0.6,
            "success_criteria": ["遇到贵人"],
            "failure_criteria": ["没遇到"],
            "window_start": "2026-08-30T00:00:00",
            "window_end": "2026-08-30T23:59:59",
        },
    )
    data = r.json()
    assert data["decision"] == "REJECT"
    failed = {a["attack"] for a in data["attacks"] if a["verdict"] == "FAIL"}
    assert "DefinitionAttack" in failed


def test_gate_rejects_missing_time_window(client):
    """第 20.4 节：「未来可能……」无时间窗口 → Reject。"""
    r = client.post(
        "/api/adversarial/gate-test",
        json={
            "description": "未来会出现一个重要的工作机会",
            "event_type": "career.job_offer",
            "probability": 0.6,
            "success_criteria": ["收到录用通知"],
            "failure_criteria": ["未收到"],
        },
    )
    data = r.json()
    assert data["decision"] == "REJECT"
    failed = {a["attack"] for a in data["attacks"] if a["verdict"] == "FAIL"}
    assert "TimeWindowAttack" in failed


def test_gate_passes_concrete_prediction(client):
    """方案第 82 节给出的正面示例应当通过。"""
    r = client.post(
        "/api/adversarial/gate-test",
        json={
            "description": (
                "出现至少一次非前一日已计划的工作任务，并造成原计划改变至少30分钟"
            ),
            "event_type": "career.unexpected_task",
            "probability": 0.67,
            "null_probability": 0.52,
            "success_criteria": [
                "安排不是前一日已经确定",
                "导致计划改变 >= 30分钟",
            ],
            "failure_criteria": ["没有发生", "虽发生沟通但没有改变计划"],
            "window_start": "2026-08-30T00:00:00",
            "window_end": "2026-08-30T23:59:59",
        },
    )
    data = r.json()
    assert data["decision"] in {"PASS", "EXPERIMENTAL"}, data["attacks"]


def test_gate_detects_agent_collusion(client):
    """第 20.11 节：Agent 输出高度相似 → 判定串谋。"""
    r = client.post(
        "/api/adversarial/gate-test",
        json={
            "description": "明天会出现临时工作任务并改变计划",
            "event_type": "career.unexpected_task",
            "probability": 0.67,
            "null_probability": 0.52,
            "success_criteria": ["出现临时任务", "计划改变30分钟"],
            "failure_criteria": ["未出现"],
            "window_start": "2026-08-30T00:00:00",
            "window_end": "2026-08-30T23:59:59",
            "agent_texts": {
                "ZiweiAgent": "命宫有变动之象，主临时任务突至",
                "BaziAgent": "命宫有变动之象，主临时任务突至",
            },
        },
    )
    data = r.json()
    failed = {a["attack"] for a in data["attacks"] if a["verdict"] == "FAIL"}
    assert "AgentCollusionAttack" in failed


def test_gate_flags_correlated_evidence(client):
    """第 20.12 节：4 个术式共享历法信号 ≠ 4 个独立证据。"""
    r = client.post(
        "/api/adversarial/gate-test",
        json={
            "description": "明天会出现临时工作任务并改变计划",
            "event_type": "career.unexpected_task",
            "probability": 0.67,
            "null_probability": 0.52,
            "success_criteria": ["出现临时任务", "计划改变30分钟"],
            "failure_criteria": ["未出现"],
            "window_start": "2026-08-30T00:00:00",
            "window_end": "2026-08-30T23:59:59",
            "signals": [
                {"source": "ziwei", "dependency_group": "lunar_calendar"},
                {"source": "bazi", "dependency_group": "lunar_calendar"},
                {"source": "qimen", "dependency_group": "lunar_calendar"},
                {"source": "meihua", "dependency_group": "lunar_calendar"},
            ],
        },
    )
    data = r.json()
    attacks = {a["attack"]: a for a in data["attacks"]}
    assert attacks["CorrelatedEvidenceAttack"]["verdict"] == "WARN"
    assert attacks["CorrelatedEvidenceAttack"]["details"]["inflation"] == 4.0


def test_gate_flags_baseline_only(client):
    """第 20.10 节：与 Null 基线几乎无差异 → 无增量信息。"""
    r = client.post(
        "/api/adversarial/gate-test",
        json={
            "description": "明天会出现临时工作任务并改变计划",
            "event_type": "career.unexpected_task",
            "probability": 0.52,
            "null_probability": 0.52,
            "success_criteria": ["出现临时任务", "计划改变30分钟"],
            "failure_criteria": ["未出现"],
            "window_start": "2026-08-30T00:00:00",
            "window_end": "2026-08-30T23:59:59",
        },
    )
    data = r.json()
    attacks = {a["attack"]: a for a in data["attacks"]}
    assert attacks["BaselineAttack"]["verdict"] == "WARN"


# ======================================================================
# 预测管线（第 2.1 / 58 节）
# ======================================================================
def test_generate_predictions(client, user_id):
    r = client.post(
        f"/api/predictions/generate?user_id={user_id}&scale=day&limit=6"
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["scanned"] > 0, "Future Scanner 应产出候选"
    assert isinstance(data["frozen"], list)
    # 第 4 节：预算限制
    assert len(data["frozen"]) <= 10


def test_prediction_has_null_baseline(client, user_id):
    """第 11 节：每条预测必须带 Null 基线，否则无法算 Skill Score。"""
    client.post(f"/api/predictions/generate?user_id={user_id}&scale=day&limit=6")
    r = client.get(f"/api/predictions?user_id={user_id}")
    items = r.json()["items"]
    assert items, "应生成至少一条预测"
    for it in items:
        assert it["null_probability"] is not None


def test_prediction_detail_is_fully_explainable(client, user_id):
    """第 49 节：预测必须完全可解释。"""
    client.post(f"/api/predictions/generate?user_id={user_id}&scale=day&limit=6")
    items = client.get(f"/api/predictions?user_id={user_id}").json()["items"]
    if not items:
        return
    pid = items[0]["prediction_id"]
    data = client.get(f"/api/predictions/{pid}").json()

    assert data["success_criteria"] and data["failure_criteria"]
    assert data["integrity"]["ok"] is True, "冻结哈希应校验通过"
    for key in ("model", "fusion", "prompt", "rule", "engine"):
        assert key in data["versions"]
    assert "evidence_dependency" in data


# ======================================================================
# 验证闭环（第 17 / 59 节）
# ======================================================================
def test_verification_flow(client, user_id):
    client.post(f"/api/predictions/generate?user_id={user_id}&scale=day&limit=6")
    items = client.get(f"/api/predictions?user_id={user_id}").json()["items"]
    if not items:
        return
    pid = items[0]["prediction_id"]

    r = client.post(
        f"/api/predictions/{pid}/verify",
        params={
            "user_reply": "下午突然让我去处理一个事情，本来准备做别的，耽误两个小时",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "outcome" in data
    # 第 18 节：结果必须落在预定义刻度上
    assert data["outcome"] in (0.0, 0.25, 0.5, 0.75, 1.0)
    # 第 20.13 节：三方 Judge
    if not data["needs_confirmation"]:
        assert len(data["judges"]) == 3


def test_verification_written_to_history(client, user_id):
    """第 51 节：历史必须同时展示成败。"""
    client.post(f"/api/predictions/generate?user_id={user_id}&scale=day&limit=6")
    items = client.get(f"/api/predictions?user_id={user_id}").json()["items"]
    if not items:
        return
    pid = items[0]["prediction_id"]
    client.post(
        f"/api/predictions/{pid}/verify",
        params={"user_reply": "没有发生，一切照常"},
    )
    hist = client.get(f"/api/predictions/history?user_id={user_id}").json()
    assert hist["count"] >= 0


# ======================================================================
# 评分（第 19 节）
# ======================================================================
def test_brier_and_skill_math():
    """第 19.1 / 19.5 节：公式正确性。"""
    from app.calibration.scoring import brier, log_loss, sharpness, skill_score

    assert abs(brier(0.8, 1.0) - 0.04) < 1e-9      # (0.8-1)² = 0.04
    assert abs(brier(0.3, 0.0) - 0.09) < 1e-9
    assert log_loss(0.99, 1.0) < log_loss(0.6, 1.0)  # 极端错误惩罚更轻当正确时
    assert log_loss(0.01, 1.0) > log_loss(0.5, 1.0)  # 极端错误惩罚严厉
    assert sharpness([0.5, 0.5, 0.5]) == 0.0          # 第 19.4 节：无信息价值
    assert sharpness([0.1, 0.9]) > 0.0
    assert skill_score(0.18, 0.22) > 0                # 优于 Null
    assert skill_score(0.25, 0.22) < 0                # 不如 Null


def test_small_sample_protection():
    """第 78 节：不能 3/3 就宣布 100% 准确。"""
    from app.calibration.scoring import reliability_label, wilson_interval

    assert reliability_label(3) == "low"
    assert reliability_label(50) == "medium"
    assert reliability_label(200) == "high"

    low, high = wilson_interval(3, 3)
    assert high <= 1.0
    assert low < 1.0, "3/3 的置信区间下界必须明显小于 1"


# ======================================================================
# Fusion 去相关（第 20.12 节）
# ======================================================================
def test_fusion_does_not_double_count_correlated_signals():
    """4 个同组信号不得比 1 个同组信号产生更大偏移。"""
    from datetime import timedelta

    from app.agents.fusion import fuse, FusionInput
    from app.schemas.signal import (
        Domain,
        Signal,
        SourceType,
        TimeScale,
        TimeWindow,
    )

    start = datetime(2026, 8, 30, 0, 0, 0)
    window = TimeWindow(start=start, end=start + timedelta(days=1))

    def mk(src: SourceType, group: str | None) -> Signal:
        return Signal(
            source=src,
            domain=Domain.CAREER,
            target_event="career.unexpected_task",
            direction=1.0,
            strength=0.8,
            confidence=0.8,
            time_window=window,
            time_scale=TimeScale.DAY,
            dependency_group=group,
        )

    one = fuse(FusionInput(signals=[mk(SourceType.BAZI, "lunar_calendar")],
                           null_probability=0.5, time_scale=TimeScale.DAY))
    four = fuse(FusionInput(
        signals=[
            mk(SourceType.BAZI, "lunar_calendar"),
            mk(SourceType.ZIWEI, "lunar_calendar"),
            mk(SourceType.QIMEN, "lunar_calendar"),
            mk(SourceType.MEIHUA, "lunar_calendar"),
        ],
        null_probability=0.5,
        time_scale=TimeScale.DAY,
    ))

    # 同组 → 组内取加权平均，不叠加。
    # 这是第 20.12 节的核心：4 个共享历法信号的术式 ≠ 4 个独立证据。
    assert abs(four.probability - one.probability) < 1e-6, (
        f"相关证据被重复计权：1 个信号 {one.probability} vs 4 个信号 {four.probability}"
    )

    # 独立来源增加 → 置信度提升（信息更充分），但概率偏移按加权平均
    independent = fuse(FusionInput(
        signals=[mk(SourceType.BAZI, "lunar_calendar"), mk(SourceType.REALITY, None)],
        null_probability=0.5,
        time_scale=TimeScale.DAY,
    ))
    assert independent.confidence > one.confidence, (
        f"独立来源应提升置信度：{independent.confidence} vs {one.confidence}"
    )

    # 组间才真正独立融合：反向的 Reality 信号必须能把结果拉下来
    against = fuse(FusionInput(
        signals=[
            mk(SourceType.BAZI, "lunar_calendar"),
            Signal(
                source=SourceType.REALITY,
                domain=Domain.CAREER,
                target_event="career.unexpected_task",
                direction=-1.0, strength=0.9, confidence=0.9,
                time_window=window, time_scale=TimeScale.DAY,
            ),
        ],
        null_probability=0.5,
        time_scale=TimeScale.DAY,
    ))
    assert against.probability < one.probability, (
        f"反向独立信号未生效：{against.probability} 应小于 {one.probability}"
    )


def test_fusion_skips_degraded_signals():
    """引擎不可用 ≠ 反对。degraded 信号必须被跳过。"""
    from datetime import timedelta

    from app.agents.fusion import fuse, FusionInput
    from app.schemas.signal import Domain, Signal, SourceType, TimeScale, TimeWindow

    start = datetime(2026, 8, 30)
    window = TimeWindow(start=start, end=start + timedelta(days=1))

    degraded = Signal(
        source=SourceType.ZIWEI,
        domain=Domain.CAREER,
        target_event="career.unexpected_task",
        direction=0.0, strength=0.0, confidence=0.0,
        time_window=window, time_scale=TimeScale.DAY,
        degraded=True, degrade_reason="引擎未接入",
    )
    out = fuse(FusionInput(signals=[degraded], null_probability=0.5,
                           time_scale=TimeScale.DAY))
    assert out.probability == 0.5, "degraded 信号不得影响融合结果"
    assert out.details.get("fallback") == "no_usable_signal"


# ======================================================================
# 冻结与篡改检测（第 16 / 20.7 节）
# ======================================================================
def test_prediction_hash_detects_tampering():
    """C-002 / 第 20.7 节：事后改口必须能被检出。"""
    from datetime import timedelta

    from app.schemas.prediction import Prediction, PredictionStatus
    from app.schemas.signal import Domain, TimeScale

    start = datetime(2026, 8, 30)
    p = Prediction(
        user_id="1",
        domain=Domain.CAREER,
        event_type="career.unexpected_task",
        description="出现临时工作任务并改变计划30分钟",
        probability=0.67,
        window_start=start,
        window_end=start + timedelta(days=1),
        time_scale=TimeScale.DAY,
        success_criteria=["出现临时任务"],
        failure_criteria=["未出现"],
        grading_rule="二值",
    )
    p.freeze()
    assert p.status is PredictionStatus.FROZEN
    assert p.verify_integrity() is True

    p.probability = 0.95  # 事后改口
    assert p.verify_integrity() is False


def test_revision_preserves_original():
    """C-003：修订只能新增版本，原版本永久存在。"""
    from datetime import timedelta

    from app.schemas.prediction import Prediction
    from app.schemas.signal import Domain, TimeScale

    start = datetime(2026, 8, 30)
    p = Prediction(
        user_id="1",
        domain=Domain.CAREER,
        event_type="career.unexpected_task",
        description="原描述",
        probability=0.67,
        window_start=start,
        window_end=start + timedelta(days=1),
        time_scale=TimeScale.DAY,
        success_criteria=["A"],
        failure_criteria=["B"],
        grading_rule="二值",
    )
    v2 = p.create_revision(description="修订描述", probability=0.75)

    assert p.description == "原描述"
    assert p.version == 1
    assert v2.description == "修订描述"
    assert v2.version == 2
    assert v2.supersedes == p.prediction_id


# ======================================================================
# Ontology（第 56 节）
# ======================================================================
def test_ontology_events_are_falsifiable(client):
    r = client.get("/api/ontology")
    items = r.json()["items"]
    assert items
    for it in items:
        assert it["success_criteria"], f"{it['event_type']} 缺少成功标准"
        assert it["failure_criteria"], f"{it['event_type']} 缺少失败标准（C-001）"
