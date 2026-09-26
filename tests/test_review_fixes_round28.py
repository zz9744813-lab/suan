"""round 28 审查修复回归：verify 死锁 / 跨站写防护 / 导出路径白名单。"""

from __future__ import annotations

import shutil
from pathlib import Path

from app.api.routes import predictions as pred_routes
from app.models.scoring import OutcomeRecord, PredictionScore
from app.schemas.outcome import Outcome


def _mk_user_and_prediction(client, user_id: int) -> str:
    """经 API 造一条可验证预测（MockProvider 链路，既有测试同款）。"""
    gen = client.post(f"/api/predictions/generate?user_id={user_id}&limit=3")
    assert gen.status_code == 200, gen.text
    preds = client.get(f"/api/predictions?user_id={user_id}").json()["items"]
    target = next(p for p in preds if p["status"] in ("FROZEN", "VERIFY_REQUIRED"))
    return target["prediction_id"]


# ----------------------------------------------------------------------
# P1：needs_confirmation 补确认死锁
# ----------------------------------------------------------------------
def test_verify_deadlock_fixed(client, user_id, monkeypatch):
    """Judge 分歧 → WAITING_USER 后，用户 quick A/B/C 补确认必须可用。

    修复前：needs_confirmation 落 OutcomeRecord 后，verify 入口见
    OutcomeRecord 即 409 —— 预测永久卡在收件箱（审查 P1 #1）。
    """

    class _FakeJudge:
        def judge(self, ctx, prediction_id: str) -> Outcome:
            return Outcome(
                prediction_id=prediction_id,
                outcome=0.5,
                confidence=0.4,
                evidence="三方 Judge 分歧（测试注入）",
                needs_confirmation=True,
                disagreement=0.8,
                verdicts=[],
            )

    monkeypatch.setattr(pred_routes, "OutcomeJudgeAgent", _FakeJudge)
    pid = _mk_user_and_prediction(client, user_id)

    # 第一轮：自然语言 verify 撞上 FakeJudge → needs_confirmation
    first = client.post(
        f"/api/predictions/{pid}/verify", params={"user_reply": "感觉还行"}
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["needs_confirmation"] is True
    assert body["status"] == "WAITING_USER"

    # 第二轮：补确认（修复点：不再 409）
    second = client.post(
        f"/api/predictions/{pid}/verify?quick_answer=A&user_id={user_id}"
    )
    assert second.status_code == 200, second.text
    confirm = second.json()
    assert confirm["outcome"] == 1.0
    assert confirm["needs_confirmation"] is False
    assert confirm["status"] == "VERIFIED"
    # 补确认轨迹进 evidence（经详情接口可查，原判定不消失）
    detail = client.get(f"/api/predictions/{pid}").json()
    assert "[补确认留痕]" in (detail["outcome"]["evidence"] or "")

    # 已计分归档后，第三次改口必须仍被 C-003 拒绝
    third = client.post(
        f"/api/predictions/{pid}/verify?quick_answer=B&user_id={user_id}"
    )
    assert third.status_code == 409


def test_verify_after_scoring_still_409(client, user_id):
    """已计分（needs_confirmation=False）的预测维持 C-003 硬禁改口。"""
    pid = _mk_user_and_prediction(client, user_id)
    ok = client.post(f"/api/predictions/{pid}/verify?quick_answer=A&user_id={user_id}")
    assert ok.status_code == 200
    assert ok.json()["status"] == "VERIFIED"
    again = client.post(f"/api/predictions/{pid}/verify?quick_answer=B&user_id={user_id}")
    assert again.status_code == 409


def test_pending_confirmation_does_not_double_score(client, user_id, monkeypatch):
    """补确认替换原行：同预测不得出现双 Outcome 行或双评分行。"""

    class _FakeJudge:
        def judge(self, ctx, prediction_id: str) -> Outcome:
            return Outcome(
                prediction_id=prediction_id,
                outcome=0.5,
                confidence=0.4,
                evidence="三方 Judge 分歧（测试注入）",
                needs_confirmation=True,
                disagreement=0.8,
            )

    monkeypatch.setattr(pred_routes, "OutcomeJudgeAgent", _FakeJudge)
    pid = _mk_user_and_prediction(client, user_id)
    client.post(f"/api/predictions/{pid}/verify", params={"user_reply": "说不好"})
    client.post(f"/api/predictions/{pid}/verify?quick_answer=A&user_id={user_id}")

    from sqlmodel import select

    from app.database import get_session
    from app.main import app

    with client:
        override = app.dependency_overrides[get_session]
        gen = override()
        session = next(gen)
        outcomes = session.exec(
            select(OutcomeRecord).where(OutcomeRecord.prediction_id == pid)
        ).all()
        scores = session.exec(
            select(PredictionScore).where(PredictionScore.prediction_id == pid)
        ).all()
        # 消费生成器收尾（Session 正常关闭由生成器 finally 处理）
        try:
            next(gen)
        except StopIteration:
            pass
    assert len(outcomes) == 1
    assert len(scores) == 1
    assert outcomes[0].outcome == 1.0


# ----------------------------------------------------------------------
# P1：跨站写防护
# ----------------------------------------------------------------------
def test_cross_site_origin_blocked(client, user_id):
    pid = _mk_user_and_prediction(client, user_id)
    evil = client.post(
        f"/api/predictions/{pid}/verify?quick_answer=A",
        headers={"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"},
    )
    assert evil.status_code == 403
    # 无 Origin 的本地客户端（curl / 调度器 / 前端同源）不受影响
    ok = client.post(f"/api/predictions/{pid}/verify?quick_answer=A&user_id={user_id}")
    assert ok.status_code == 200


def test_generate_cross_site_blocked(client, user_id):
    blocked = client.post(
        f"/api/predictions/generate?user_id={user_id}",
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert blocked.status_code == 403


# ----------------------------------------------------------------------
# P1：Obsidian 导出路径白名单
# ----------------------------------------------------------------------
def test_export_rejects_path_outside_data(client, user_id, tmp_path):
    for bad in ("C:/Windows/Temp", "../../", str(tmp_path)):
        resp = client.get(
            "/api/export/obsidian", params={"user_id": user_id, "base_dir": bad}
        )
        assert resp.status_code == 403, f"{bad} 应被拒绝"


def test_export_allows_data_subdir(client, user_id):
    out = Path.cwd() / "data" / "obsidian_r28_test"
    try:
        resp = client.get(
            "/api/export/obsidian",
            params={"user_id": user_id, "base_dir": str(out)},
        )
        assert resp.status_code == 200, resp.text
        assert (out / "00_仪表盘.md").exists()
    finally:
        shutil.rmtree(out, ignore_errors=True)
