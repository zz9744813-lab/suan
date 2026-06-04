"""P1 smoke test: 直接用 FastAPI TestClient 验证 17 端点.

不依赖外部 backend 进程, 也不依赖 pytest (Windows pytest capture
bug, 见 R*/P* 测试约定).
"""
import asyncio
import json
import sys
from datetime import datetime, timedelta

# 让 import 找得到 app.*
sys.path.insert(0, r"F:\kelaode\Data\Agents\zhongji8633\wudi8633\backend")

import httpx
from app.main import app


BASE = "http://testserver/api"


def step(n: int, name: str) -> None:
    print(f"\n[STEP {n}] {name}")


def check(label: str, ok: bool, detail: str = "") -> None:
    icon = "OK " if ok else "FAIL"
    msg = f"  [{icon}] {label}"
    if detail:
        msg += f"  ({detail})"
    print(msg)
    if not ok:
        raise AssertionError(f"{label}: {detail}")


async def main() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url=BASE,
    ) as client:
        # ------------------------------------------------------------
        step(1, "GET /api/reviews/reader-profiles — 5 个默认 reader")
        # ------------------------------------------------------------
        r = await client.get("/reviews/reader-profiles")
        check("status 200", r.status_code == 200, str(r.status_code))
        d = r.json()["data"]
        check("ok=true", r.json()["ok"])
        check("5 个 profile", len(d) == 5, f"got {len(d)}")
        keys = sorted(p["reader_key"] for p in d)
        check(
            "5 个 key 都对",
            keys == sorted([
                "reader_commercial", "reader_emotion", "reader_hook",
                "reader_logic", "reader_toxic",
            ]),
            str(keys),
        )
        check(
            "weight 默认 1.0",
            all(p["weight"] == 1.0 for p in d),
        )
        check("enabled=True", all(p["enabled"] for p in d))

        # ------------------------------------------------------------
        step(2, "GET /api/reviews/settings?project_id=2 — 缺省创建 (project 2 没改过)")
        # ------------------------------------------------------------
        r = await client.get("/reviews/settings?project_id=2")
        check("status 200", r.status_code == 200)
        s = r.json()["data"]
        check("retention_days=7", s["retention_days"] == 7, str(s))
        check("auto_reader_review=true", s["auto_reader_review"] is True)
        check(
            "min_severity=medium",
            s["min_severity_for_discussion"] == "medium",
        )

        # ------------------------------------------------------------
        step(3, "PUT /api/reviews/settings?project_id=1 — 改设置")
        # ------------------------------------------------------------
        r = await client.put(
            "/reviews/settings?project_id=1",
            json={"retention_days": 14, "max_reader_comments_per_run": 3},
        )
        check("status 200", r.status_code == 200)
        s = r.json()["data"]
        check("retention_days=14", s["retention_days"] == 14)
        check("max_reader_comments_per_run=3", s["max_reader_comments_per_run"] == 3)
        # 其余字段保留
        check("auto_reader_review 保留", s["auto_reader_review"] is True)

        # ------------------------------------------------------------
        step(4, "POST /api/reviews/comments — user 发评论")
        # ------------------------------------------------------------
        r = await client.post(
            "/reviews/comments",
            json={
                "project_id": 1,
                "chapter_id": 13,  # project 1 的 chapter 1, id=13
                "author_type": "user",
                "author_label": "朱十一",
                "content": "女主转变缺少触发点",
                "tags": ["人物动机"],
                "priority": 70,
            },
        )
        if r.status_code == 400 and "Chapter" in r.text:
            r2 = await client.get("/chapters?project_id=1")
            print("  chapters:", r2.json())
            raise AssertionError("需要 project 1 有 chapter")
        check("status 201", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
        c1 = r.json()["data"]
        check("id 分配", c1["id"] > 0)
        check("status=new", c1["status"] == "new")
        check("expires_at 已设", c1["expires_at"] is not None)
        check("author_type=user", c1["author_type"] == "user")
        # 验证 expires_at 是 14 天后 (我们刚改了 retention_days=14)
        exp = datetime.fromisoformat(c1["expires_at"].replace("Z", "+00:00"))
        delta_days = (exp.replace(tzinfo=None) - datetime.utcnow()).days
        check("expires_at ~14 天后", 13 <= delta_days <= 14, f"delta={delta_days}d")

        # ------------------------------------------------------------
        step(5, "POST /api/reviews/comments — reader_agent 模拟评论")
        # ------------------------------------------------------------
        r = await client.post(
            "/reviews/comments",
            json={
                "project_id": 1,
                "chapter_id": 13,
                "author_type": "reader_agent",
                "author_label": "Reader·情绪",
                "agent_role_id": 13,  # reader_emotion (per seed)
                "content": "女主从怀疑到出手缺一个 trigger",
                "rating": {"score": 65, "dimensions": {"emotion_arc": 60}},
                "tags": ["情绪递进", "人物动机"],
                "weight_at_created": 1.0,
            },
        )
        check("status 201", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
        c2 = r.json()["data"]
        check("author_type=reader_agent", c2["author_type"] == "reader_agent")
        check("rating 已存", c2["rating"]["score"] == 65)

        # ------------------------------------------------------------
        step(6, "POST /reviews/comments/{id}/reply — chief_agent 回复")
        # ------------------------------------------------------------
        r = await client.post(
            f"/reviews/comments/{c1['id']}/reply",
            json={"content": "已接入, 准备合并情绪读者的意见", "tags": ["chief_reply"]},
        )
        check("status 201", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
        reply = r.json()["data"]
        check("parent_id=c1.id", reply["parent_id"] == c1["id"])
        check("author_type=chief_agent", reply["author_type"] == "chief_agent")

        # 父评论 status 推进
        r = await client.get(f"/reviews/comments/{c1['id']}")
        parent = r.json()["data"]
        check("父评论 status=replied", parent["status"] == "replied")
        check("replies 包含 chief_agent", len(parent["replies"]) >= 1)
        check("replies[0]=chief_agent", parent["replies"][0]["author_type"] == "chief_agent")

        # ------------------------------------------------------------
        step(7, "GET /api/reviews/comments — 列表 + 过滤")
        # ------------------------------------------------------------
        r = await client.get("/reviews/comments?project_id=1")
        check("status 200", r.status_code == 200)
        lst = r.json()["data"]
        check("total >= 3", lst["total"] >= 3, f"total={lst['total']}")
        # user 评论 + reader_agent 评论 + chief_agent 回复

        r = await client.get(
            "/reviews/comments?project_id=1&author_type=user",
        )
        user_only = r.json()["data"]
        check(
            "user_only 全部是 user",
            all(c["author_type"] == "user" for c in user_only["items"]),
        )

        # ------------------------------------------------------------
        step(8, "POST /api/reviews/groups — 合并 2 条评论入组")
        # ------------------------------------------------------------
        r = await client.post(
            "/reviews/groups",
            json={
                "project_id": 1,
                "chapter_id": 13,
                "title": "女主转变可信度不足",
                "summary": "user + 情绪读者 都指出女主缺触发点",
                "comment_ids": [c1["id"], c2["id"]],
                "severity": "high",
            },
        )
        check("status 201", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
        g1 = r.json()["data"]
        check("status=new", g1["status"] == "new")
        check("severity=high", g1["severity"] == "high")
        check("comment_ids 含 2 条", len(g1["comment_ids"]) == 2)

        # 关联评论 status 自动变 grouped
        r = await client.get(f"/reviews/comments/{c1['id']}")
        check("c1.status=grouped", r.json()["data"]["status"] == "grouped")
        check(
            "c1.related_group_id=g1.id",
            r.json()["data"]["related_group_id"] == g1["id"],
        )

        # ------------------------------------------------------------
        step(9, "GET /api/reviews/groups/{id} — 详情 + 展开评论")
        # ------------------------------------------------------------
        r = await client.get(f"/reviews/groups/{g1['id']}")
        check("status 200", r.status_code == 200)
        gd = r.json()["data"]
        check("comments 含 2 条", len(gd["comments"]) == 2)

        # ------------------------------------------------------------
        step(10, "POST /api/reviews/groups/{id}/discuss — 转讨论")
        # ------------------------------------------------------------
        r = await client.post(
            f"/reviews/groups/{g1['id']}/discuss",
            json={
                "participant_keys": ["planner", "critic", "continuity"],
                "note": "影响主线节奏, 立即讨论",
            },
        )
        check("status 200", r.status_code == 200)
        check("status=discussing", r.json()["data"]["status"] == "discussing")

        # ------------------------------------------------------------
        step(11, "POST /api/reviews/groups/{id}/decide — 主 Agent 写裁决")
        # ------------------------------------------------------------
        r = await client.post(
            f"/reviews/groups/{g1['id']}/decide",
            json={
                "decision": "local_rewrite",
                "accepted_comment_ids": [c1["id"]],
                "rejected_comment_ids": [c2["id"]],
                "rewrite_instruction": "在第 5 段后加一个 trigger 事件",
                "validation_plan": "重跑 reader_emotion, score >= 80",
            },
        )
        check("status 200", r.status_code == 200)
        gd = r.json()["data"]
        check("status=rewrite_queued", gd["status"] == "rewrite_queued")
        check("decision.decision=local_rewrite", gd["decision"]["decision"] == "local_rewrite")

        # 评论状态推进
        r = await client.get(f"/reviews/comments/{c1['id']}")
        check("c1.status=accepted", r.json()["data"]["status"] == "accepted")
        r = await client.get(f"/reviews/comments/{c2['id']}")
        check("c2.status=rejected", r.json()["data"]["status"] == "rejected")

        # ------------------------------------------------------------
        step(12, "POST /api/reviews/runs — 内部触发读者评审")
        # ------------------------------------------------------------
        r = await client.post(
            "/reviews/runs",
            json={
                "project_id": 1,
                "chapter_id": 13,
                "trigger": "manual_test",
            },
        )
        check("status 201", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
        run = r.json()["data"]
        check("status=pending", run["status"] == "pending")
        check(
            "5 个 reader key 都填了",
            sorted(run["reader_agent_keys"]) == sorted([
                "reader_hook", "reader_emotion", "reader_logic",
                "reader_commercial", "reader_toxic",
            ]),
        )

        # ------------------------------------------------------------
        step(13, "GET /api/reviews/runs — 列出")
        # ------------------------------------------------------------
        r = await client.get("/reviews/runs?project_id=1")
        check("status 200", r.status_code == 200)
        runs = r.json()["data"]
        check(">= 1 run", len(runs) >= 1)

        # ------------------------------------------------------------
        step(14, "GET /api/reviews/runs/{id} — 详情")
        # ------------------------------------------------------------
        r = await client.get(f"/reviews/runs/{run['id']}")
        check("status 200", r.status_code == 200)
        check("id 一致", r.json()["data"]["id"] == run["id"])

        # ------------------------------------------------------------
        step(15, "POST /api/reviews/cleanup — 过期清理")
        # ------------------------------------------------------------
        r = await client.post("/reviews/cleanup?project_id=1")
        check("status 200", r.status_code == 200)
        d = r.json()["data"]
        check("deleted 是 int", isinstance(d["deleted"], int))
        # 我们刚发的评论 expires_at 是 14 天后, 不会删
        check("deleted=0 (无过期)", d["deleted"] == 0, f"got {d['deleted']}")

        # ------------------------------------------------------------
        step(16, "DELETE /api/reviews/comments/{id} — 硬删评论")
        # ------------------------------------------------------------
        # 先建一个临时评论用于删除
        r = await client.post(
            "/reviews/comments",
            json={
                "project_id": 1,
                "author_type": "user",
                "author_label": "test",
                "content": "to be deleted",
            },
        )
        temp_id = r.json()["data"]["id"]
        r = await client.delete(f"/reviews/comments/{temp_id}")
        check("status 200", r.status_code == 200)
        # 再 GET 应该 404
        r = await client.get(f"/reviews/comments/{temp_id}")
        check("status 404", r.status_code == 404)

        # ------------------------------------------------------------
        step(17, "PATCH /api/reviews/groups/{id} — 改 title/severity")
        # ------------------------------------------------------------
        r = await client.patch(
            f"/reviews/groups/{g1['id']}",
            json={"title": "女主转变可信度不足 (重命名)", "severity": "blocker"},
        )
        check("status 200", r.status_code == 200)
        check("title 已改", "重命名" in r.json()["data"]["title"])
        check("severity=blocker", r.json()["data"]["severity"] == "blocker")

        print("\n[ALL GREEN] 17 端点全通过.")


if __name__ == "__main__":
    asyncio.run(main())
