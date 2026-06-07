"""L4 test_08_reader_review_discussion.py — 评论/读者评审/讨论轻量契约。"""
from __future__ import annotations

import pytest


async def make_project_chapter(db):
    from app.models.project import Chapter, Project

    project = Project(
        name="评论讨论测试",
        genre="玄幻",
        target_word_count=100_000,
        target_chapter_count=100,
    )
    db.add(project)
    await db.flush()
    chapter = Chapter(
        project_id=project.id,
        chapter_no=1,
        title="开局章",
        target_word_count=3000,
    )
    db.add(chapter)
    await db.flush()
    await db.commit()
    return project, chapter


async def create_comment(client, project_id: int, chapter_id: int, content: str = "节奏这里偏慢"):
    r = await client.post("/api/reviews/comments", json={
        "project_id": project_id,
        "chapter_id": chapter_id,
        "target_type": "chapter",
        "author_type": "user",
        "author_label": "测试读者",
        "content": content,
        "tags": ["pace"],
        "priority": 80,
    })
    assert r.status_code == 201
    return r.json()["data"]


@pytest.mark.asyncio
class TestReaderReviewDiscussion:
    async def test_comment_lifecycle_light(self, client, db):
        project, chapter = await make_project_chapter(db)
        comment = await create_comment(client, project.id, chapter.id)
        assert comment["status"] == "new"
        assert comment["expires_at"] is not None

        listed = await client.get(f"/api/reviews/comments?project_id={project.id}&include_replies=false")
        assert listed.status_code == 200
        data = listed.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["content"] == "节奏这里偏慢"

    async def test_group_discuss_and_decide(self, client, db):
        project, chapter = await make_project_chapter(db)
        c1 = await create_comment(client, project.id, chapter.id, "节奏慢")
        c2 = await create_comment(client, project.id, chapter.id, "冲突不够尖锐")

        group_resp = await client.post("/api/reviews/groups", json={
            "project_id": project.id,
            "chapter_id": chapter.id,
            "title": "开局节奏问题",
            "summary": "两条评论都指向开局吸引力不足",
            "comment_ids": [c1["id"], c2["id"]],
            "severity": "high",
        })
        assert group_resp.status_code == 201
        group = group_resp.json()["data"]
        assert group["status"] == "new"
        assert group["comment_ids"] == [c1["id"], c2["id"]]

        comments_after_group = await client.get(f"/api/reviews/comments?group_id={group['id']}")
        assert comments_after_group.status_code == 200
        assert comments_after_group.json()["data"]["total"] == 2
        assert {c["status"] for c in comments_after_group.json()["data"]["items"]} == {"grouped"}

        discuss_resp = await client.post(f"/api/reviews/groups/{group['id']}/discuss", json={
            "participant_keys": ["planner", "critic"],
            "note": "请聚焦第一章钩子",
        })
        assert discuss_resp.status_code == 200
        discussing = discuss_resp.json()["data"]
        assert discussing["status"] == "discussing"
        assert discussing["discussion_session_id"] is not None

        decision_resp = await client.post(f"/api/reviews/groups/{group['id']}/decide", json={
            "decision": "light_fix",
            "accepted_comment_ids": [c1["id"]],
            "rejected_comment_ids": [c2["id"]],
            "validation_plan": "重看前 500 字节奏",
        })
        assert decision_resp.status_code == 200
        decided = decision_resp.json()["data"]
        assert decided["status"] == "rewrite_queued"
        assert decided["decision"]["decision"] == "light_fix"

    async def test_group_not_found_contract(self, client):
        r = await client.post("/api/reviews/groups/99999/decide", json={"decision": "no_change"})
        assert r.status_code == 404
