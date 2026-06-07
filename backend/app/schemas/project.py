"""Project / chapter / bible / outline schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    genre: str = Field(default="玄幻")
    target_word_count: int = Field(default=3_000_000)
    target_chapter_count: int = Field(default=2000)
    description: str | None = None
    # Round 2 (P0-UI-2): let the create form start with a category
    # so the project lands in the right group on day one. Optional —
    # the router falls back to ``genre`` when omitted.
    category: str | None = None
    pinned: bool = False


class ProjectUpdate(BaseModel):
    name: str | None = None
    genre: str | None = None
    target_word_count: int | None = None
    target_chapter_count: int | None = None
    description: str | None = None
    status: str | None = None
    # Round 2: PATCH supports category, pinned, sort_order, and an
    # explicit ``last_opened_at`` touch (the router stamps it to
    # ``utcnow`` when the client just sets ``touch_last_opened=True``).
    category: str | None = None
    pinned: bool | None = None
    sort_order: int | None = None
    touch_last_opened: bool | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    genre: str
    # Round 2: ``category`` is the grouping key the ProjectNav uses
    # (genre when category is null). ``sort_order`` orders within a
    # group; ``pinned`` floats the project above non-pinned peers;
    # ``last_opened_at`` powers the MRU badge in the chief panel.
    category: str | None = None
    sort_order: int = 0
    pinned: bool = False
    last_opened_at: datetime | None = None
    target_word_count: int
    target_chapter_count: int
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    chapter_count: int = 0
    total_words: int = 0


class ProjectReorderItem(BaseModel):
    """One entry in a ``POST /projects/reorder`` payload."""
    project_id: int
    sort_order: int = 0
    category: str | None = None
    pinned: bool = False


class ProjectReorderRequest(BaseModel):
    """Batch update used by the drag-and-drop frontend."""
    items: list[ProjectReorderItem]


class BibleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    title: str
    content: dict[str, Any]
    version: int
    is_active: bool
    updated_at: datetime


class BibleUpdate(BaseModel):
    title: str | None = None
    content: dict[str, Any] | None = None


class OutlineCreate(BaseModel):
    volume_no: int = 1
    chapter_no: int
    title: str
    summary: str | None = None
    importance: int = 50
    is_arc_peak: bool = False
    is_volume_climax: bool = False
    is_volume_opener: bool = False
    target_word_count: int = 3000


class OutlineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    volume_no: int
    chapter_no: int
    title: str
    summary: str | None
    importance: int
    is_arc_peak: bool
    is_volume_climax: bool
    is_volume_opener: bool
    target_word_count: int
    status: str


class ChapterCreate(BaseModel):
    outline_id: int | None = None
    chapter_no: int
    title: str
    target_word_count: int = 3000


class ChapterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    outline_id: int | None
    chapter_no: int
    title: str
    target_word_count: int
    actual_word_count: int
    status: str
    current_score: int | None
    updated_at: datetime


class ChapterVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    version_kind: str
    version_no: int
    content: str
    summary: str | None
    score: int | None
    notes: dict[str, Any] | None
    created_at: datetime


class ProjectWorkspaceTocItem(BaseModel):
    chapter_no: int
    title: str
    outline_id: int | None = None
    chapter_id: int | None = None
    outline_summary: str | None = None
    target_word_count: int = 0
    actual_word_count: int = 0
    status: str = "outline"
    has_content: bool = False
    selected: bool = False


class ProjectWorkspaceChapter(BaseModel):
    id: int
    chapter_no: int
    title: str
    status: str
    target_word_count: int
    actual_word_count: int
    current_score: int | None = None
    outline_id: int | None = None
    outline_summary: str | None = None
    version_id: int | None = None
    version_kind: str | None = None
    version_no: int | None = None
    version_score: int | None = None
    summary: str | None = None
    content: str = ""
    updated_at: datetime


class ProjectWorkspaceResponse(BaseModel):
    project: ProjectRead
    bible: BibleRead | None = None
    characters: list[Any] = Field(default_factory=list)
    toc: list[ProjectWorkspaceTocItem] = Field(default_factory=list)
    selected_chapter: ProjectWorkspaceChapter | None = None
    latest_tasks: list[Any] = Field(default_factory=list)


class ProjectLaunchRequest(BaseModel):
    """双模式创作启动请求。"""
    mode: str = Field(..., description="启动模式: semi_auto | full_auto")
    # 模式一 (semi_auto) 的输入
    outline_text: str | None = Field(default=None, description="大纲文本 (管道符/JSON/纯文本格式)")
    character_text: str | None = Field(default=None, description="人物设定文本")
    bible_text: str | None = Field(default=None, description="世界观/设定文本")
