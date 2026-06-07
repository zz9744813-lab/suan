from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_project_workspace_returns_book_second_layer(client, db):
    from app.core.database import init_db
    from app.models.memory import MemoryCharacter, MemoryCharacterState
    from app.models.project import Bible, Chapter, ChapterVersion, Outline, Project
    from app.models.task import AgentTask

    await init_db()

    project = Project(
        name="Second Layer Book",
        genre="fantasy",
        target_word_count=100000,
        target_chapter_count=10,
    )
    db.add(project)
    await db.flush()
    bible = Bible(
        project_id=project.id,
        title="Main Bible",
        content={
            "world": "A city built on stacked moons.",
            "rules": ["Moonlight powers contracts."],
            "main_plot": "Find the missing lower moon.",
        },
        is_active=True,
    )
    outline = Outline(
        project_id=project.id,
        chapter_no=1,
        title="Arrival",
        summary="The protagonist enters the moon city.",
        target_word_count=3000,
    )
    db.add_all([bible, outline])
    await db.flush()
    chapter = Chapter(
        project_id=project.id,
        outline_id=outline.id,
        chapter_no=1,
        title="Arrival",
        actual_word_count=1200,
        status="done",
    )
    db.add(chapter)
    await db.flush()
    db.add_all([
        ChapterVersion(
            chapter_id=chapter.id,
            version_kind="draft",
            version_no=1,
            content="draft text",
        ),
        ChapterVersion(
            chapter_id=chapter.id,
            version_kind="final",
            version_no=1,
            content="final text",
            summary="final summary",
            score=88,
        ),
    ])
    character = MemoryCharacter(
        project_id=project.id,
        name="Lin",
        role="protagonist",
        base_profile={"description": "A contract cartographer."},
    )
    db.add(character)
    await db.flush()
    db.add(MemoryCharacterState(
        character_id=character.id,
        project_id=project.id,
        chapter_no=1,
        current_location="Moon gate",
        current_goal="Map the missing moon",
    ))
    db.add(AgentTask(
        project_id=project.id,
        chapter_id=chapter.id,
        task_type="chapter_pipeline",
        status="succeeded",
        priority=100,
    ))
    await db.commit()

    response = await client.get(f"/api/projects/{project.id}/workspace")
    assert response.status_code == 200
    payload = response.json()["data"]

    assert payload["project"]["name"] == "Second Layer Book"
    assert payload["bible"]["content"]["world"] == "A city built on stacked moons."
    assert payload["toc"][0]["chapter_no"] == 1
    assert payload["toc"][0]["has_content"] is True
    assert payload["selected_chapter"]["content"] == "final text"
    assert payload["selected_chapter"]["version_kind"] == "final"
    assert payload["characters"][0]["name"] == "Lin"
    assert payload["latest_tasks"][0]["task_type"] == "chapter_pipeline"
