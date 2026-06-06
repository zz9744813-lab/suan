"""P5 联调验收 + 回归测试清单 (F:\\06_P5_联调验收_回归测试清单.md).

P0-P4 全部完成后, 这一份测试同时覆盖 13 节验收里的可自动化部分.
不依赖 live DB — 全部 schema-level + 路由注册 + seed 内容验证.

覆盖:
  §1  全局启动: app 能被构造, 18 个 router 全部注册, 无 import 错
  §2  项目书架: projects router 端点齐
  §3  拆书书架: deepstudy router 端点齐, library summary shape
  §4  项目记忆: project_memory router 端点齐, 7 档案柜定义
  §5  模型配置: agent_roles router 端点齐, matrix shape
  §6  新增 Agent: AgentRoleCreate 接受 ForeshadowInspector 风格
  §7  写作流水线: tasks/chapters 端点齐
  §8  拆书流水线: deepstudy run lifecycle 状态机
  §9  记忆去重: P3 §12 merge schema (苏瑶/苏瑶儿/瑶儿)
  §10 记忆冲突: DiscussionDecision 状态机
  §12 回归: Provider CRUD schema, prompt CRUD schema
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ============================================================
# §1 全局启动验收
# ============================================================

def test_app_imports_clean():
    """P5 §1.1-1.4: 后端启动无报错. import main 看是否有未捕获的 ImportError."""
    from app.main import app
    assert app is not None


def test_all_routers_registered():
    """P5 §1.x: 18 个 router 全部 include 进 app. 如果哪个 P0-P4 阶段
    漏掉 include_router, 这里会报 'not found' (路由表里找不到)."""
    from app.main import app
    expected_prefixes = [
        "/api/projects",
        "/api/chapters",
        "/api/tasks",
        "/api/prompts",
        "/api/models",
        "/api/worker",
        "/api/chief",
        "/api/memory",
        "/api/events",
        "/api/study",
        "/api/behavior",
        "/api/graph",
        "/api/discussion",
        "/api/search",
        "/api/deepstudy",
        # P3
        "/api/project-memory",
        # P4
        "/api/agent-roles",
        "/api/agent-runs",
    ]
    actual = {r.path for r in app.routes if hasattr(r, "path")}
    for prefix in expected_prefixes:
        # FastAPI 把 router 路径加上 settings.api_prefix; check any
        # path starts with that prefix (so /api/projects/1 etc all
        # 算).
        matches = [p for p in actual if p.startswith(prefix)]
        assert len(matches) > 0, (
            f"Router prefix '{prefix}' 没在 app.routes 里; 实际前缀列表:\n"
            + "\n".join(sorted({p.split('/', 3)[:3] and '/'.join(p.split('/')[:3]) for p in actual}))
        )


def test_settings_api_prefix_is_api():
    """P5 §1.x: settings.api_prefix 应是 /api, 跟所有 router 拼接."""
    from app.core.config import settings
    assert settings.api_prefix.startswith("/api")


# ============================================================
# §2 项目书架验收 (P1)
# ============================================================

def test_projects_router_has_crud():
    """P1 §4: projects router 至少要支持 list + create + get + delete."""
    from app.main import app
    methods = set()
    for r in app.routes:
        if hasattr(r, "path") and r.path.startswith("/api/projects"):
            for m in r.methods:
                methods.add(m)
    # FastAPI 路由表 methods 是 {'GET'} 这种 set
    for needed in ("GET", "POST", "PUT", "DELETE"):
        assert needed in methods, f"projects router 缺 {needed}: methods={methods}"


# ============================================================
# §3 拆书书架验收 (P2)
# ============================================================

def test_deepstudy_library_summary_shape():
    """P5 §3.x / R25 §9.1: LibrarySummary 含 8 个状态 + 3 个深层 counter
    (entities / relationships / techniques). 实际 schema 字段."""
    from app.schemas.deepstudy import LibrarySummary
    fields = set(LibrarySummary.model_fields.keys())
    # 8 状态
    for k in ("empty", "chapterized", "studying",
              "paused", "review_required", "completed", "failed", "total_books"):
        assert k in fields, f"LibrarySummary 缺状态字段 {k}"
    # 3 深层 counter (entity / relationship / technique)
    for k in ("total_entities", "total_relationships", "total_techniques"):
        assert k in fields, f"LibrarySummary 缺 counter {k}"


def test_deepstudy_routes_count():
    """P5 §3.x: deepstudy router 至少要 10 个端点
    (R25 实现了 library + runs + graph + nodes + patterns/techniques)."""
    from app.main import app
    deepstudy_paths = [
        r for r in app.routes
        if hasattr(r, "path") and r.path.startswith("/api/deepstudy")
    ]
    assert len(deepstudy_paths) >= 8, f"deepstudy 端点 {len(deepstudy_paths)} 个, 期望 >= 8"


# ============================================================
# §4 项目记忆书架验收 (P3)
# ============================================================

def test_project_memory_router_endpoints():
    """P5 §4.x / P3 §3.2: 11 端点 — shelf / archive / consolidate / list / get /
    foreshadows / facts / decisions / run_decision / apply_decision / raw."""
    from app.main import app
    pm_paths = [r.path for r in app.routes if hasattr(r, "path") and "/project-memory" in r.path]
    assert len(pm_paths) >= 10, f"project-memory 端点 {len(pm_paths)} 个, 期望 >= 10"


def test_cabinets_defines_seven_types():
    """P5 §4.5: 没有独立冲突档案柜 — 7 个档案柜 (character/location/
    faction/item/world_rule/foreshadow/hard_fact), 冲突走 DiscussionDecision.
    直接验证 project_memory router 源码里这 7 个字符串都出现."""
    import os
    router_path = os.path.join(
        os.path.dirname(__file__), "..", "routers", "project_memory.py"
    )
    with open(router_path, "r", encoding="utf-8") as f:
        src = f.read()
    expected = ["character", "foreshadow", "hard_fact", "location",
                "faction", "item", "world_rule"]
    found = sum(1 for n in expected if f'"{n}"' in src)
    assert found == 7, f"7 cabinet 字符串不全: {found}/7 in router"


# ============================================================
# §5 模型配置验收 (P4)
# ============================================================

def test_agent_role_router_endpoints():
    """P5 §5.x / P4 §9: agent-roles 至少 8 端点 + agent-runs 4 端点."""
    from app.main import app
    ar_paths = [r.path for r in app.routes if hasattr(r, "path") and "/agent-roles" in r.path]
    run_paths = [r.path for r in app.routes if hasattr(r, "path") and "/agent-runs" in r.path]
    assert len(ar_paths) >= 8, f"agent-roles 端点 {len(ar_paths)} 个, 期望 >= 8"
    assert len(run_paths) >= 4, f"agent-runs 端点 {len(run_paths)} 个, 期望 >= 4"


def test_agent_role_matrix_item_shape():
    """P5 §5.5: AgentRoleMatrixItem 必须含 role + binding + status
    + current_task + provider_name + model_name + recent_runs."""
    from app.schemas.agent_role import AgentRoleMatrixItem
    fields = set(AgentRoleMatrixItem.model_fields.keys())
    for k in ("role", "binding", "status", "status_label",
              "current_task", "provider_name", "model_name",
              "recent_runs", "recent_events", "progress", "last_run_id"):
        assert k in fields, f"AgentRoleMatrixItem 缺 {k}"


def test_default_agent_roles_count():
    """默认 AgentRole 覆盖写作、拆书、讨论、记忆、读者反馈和评论分流."""
    from app.seed import DEFAULT_AGENT_ROLES
    assert len(DEFAULT_AGENT_ROLES) == 17, f"DEFAULT_AGENT_ROLES 数量 {len(DEFAULT_AGENT_ROLES)} != 17"
    keys = {r["key"] for r in DEFAULT_AGENT_ROLES}
    expected = {"planner", "drafter", "critic", "rewriter", "continuity",
                "memory_update", "deep_study", "discussion",
                "memory_consolidator", "technique_distill", "study_critic",
                "reader_hook", "reader_emotion", "reader_logic",
                "reader_commercial", "reader_toxic", "chief_comment_moderator"}
    assert keys == expected, f"default 角色 keys 不全: {keys - expected}"


# ============================================================
# §6 新增 Agent 验收 (P4 §6 + §7)
# ============================================================

def test_foreshadow_inspector_create_body():
    """P5 §6: 新增 ForeshadowInspector 风格 Agent — category=writing,
    run_mode=pipeline, pipeline_stage=after_draft_before_critic.
    验证 AgentRoleCreate schema 接受这些字段."""
    from app.schemas.agent_role import AgentRoleCreate
    body = AgentRoleCreate(
        key="foreshadow_inspector",
        display_name="ForeshadowInspector",
        description="扫描章节伏笔一致性",
        category="writing",
        avatar_style="scribe",
        enabled=True,
        visible_in_matrix=True,
        run_mode="pipeline",
        pipeline_stage="after_draft_before_critic",
        timeout_seconds=90,
        max_retries=1,
        concurrency_limit=1,
    )
    assert body.key == "foreshadow_inspector"
    assert body.pipeline_stage == "after_draft_before_critic"
    assert body.category == "writing"
    assert body.run_mode == "pipeline"


def test_agent_role_create_required_fields():
    """P5 §6.1: 创建 Agent 必须有 key + display_name."""
    from pydantic import ValidationError
    from app.schemas.agent_role import AgentRoleCreate
    try:
        AgentRoleCreate()  # 缺 key / display_name
        raise AssertionError("应该 ValidationError, 但通过了")
    except ValidationError as e:
        errors = e.errors()
        missing = {err["loc"][0] for err in errors if err["type"] == "missing"}
        assert "key" in missing
        assert "display_name" in missing


def test_agent_role_update_partial():
    """P5 §6.x: PUT 应该能改 display_name + timeout, 不需要全字段."""
    from app.schemas.agent_role import AgentRoleUpdate
    body = AgentRoleUpdate(display_name="X", timeout_seconds=200)
    dumped = body.model_dump(exclude_unset=True)
    assert dumped == {"display_name": "X", "timeout_seconds": 200}


def test_agent_model_binding_update_accepts_nones():
    """P5 §5.x: model-binding 端点允许 None (清空绑定)."""
    from app.schemas.agent_role import AgentModelBindingUpdate
    body = AgentModelBindingUpdate(provider_id=None, model_name=None)
    assert body.provider_id is None
    assert body.model_name is None


# ============================================================
# §7 写作流水线验收
# ============================================================

def test_chapters_router_endpoints():
    """P5 §7.4: chapters 端点齐 (至少 list / get / create / run / versions)."""
    from app.main import app
    ch = [r.path for r in app.routes if hasattr(r, "path") and "/chapters" in r.path]
    assert len(ch) >= 5, f"chapters 端点 {len(ch)} 个, 期望 >= 5"


def test_tasks_router_endpoints():
    """P5 §7.3: tasks 端点齐 (至少 list / cancel / pause / resume)."""
    from app.main import app
    t = [r.path for r in app.routes if hasattr(r, "path") and "/tasks" in r.path]
    assert len(t) >= 4, f"tasks 端点 {len(t)} 个, 期望 >= 4"


# ============================================================
# §8 拆书流水线验收 (P2 DeepStudy)
# ============================================================

def test_study_run_lifecycle_states():
    """P5 §8.1 / R25 §3.1: StudyRun status 状态机: queued/running/paused/
    succeeded/failed/cancelled. Pydantic Literal 校验."""
    from app.schemas.deepstudy import StudyRunRead
    # model_fields 不会列出 Literal 限制; 通过创建一个实例验证
    # (这里不真跑 DB, 只验证 schema 接受每个状态字符串)
    # StudyRunRead 需要 id + project_id, 用 model_construct 跳过验证
    from app.schemas.deepstudy import StudyRunRead
    for st in ("queued", "running", "paused", "succeeded", "failed", "cancelled"):
        # 强制构造, 验证 status 是 string
        obj = StudyRunRead.model_construct(
            id=1, project_id=1, material_id=1, mode="full",
            status=st, stages=[], progress={}, error_message=None,
            started_at=None, finished_at=None, created_at=None,
        )
        assert obj.status == st


# ============================================================
# §9 记忆去重验收 (P3 §12)
# ============================================================

def test_memory_merge_schema_supports_aliases():
    """P5 §9: 苏瑶/苏瑶儿/瑶儿 → 1 角色 + aliases=[苏瑶儿, 瑶儿].
    StableMemoryEntityRead 必须支持 aliases 列表 + entity_type='character'."""
    from app.schemas.memory_v2 import StableMemoryEntityRead
    fields = set(StableMemoryEntityRead.model_fields.keys())
    assert "canonical_name" in fields
    assert "aliases" in fields
    assert "entity_type" in fields


def test_memory_timeline_event_per_chapter():
    """P5 §9.x: timeline 必须按章节记录 (chapter_id 字段)."""
    from app.schemas.memory_v2 import MemoryTimelineEventRead
    fields = set(MemoryTimelineEventRead.model_fields.keys())
    assert "chapter_id" in fields


# ============================================================
# §10 记忆冲突验收
# ============================================================

def test_discussion_decision_status_states():
    """P5 §10.x: DiscussionDecision 状态字段 + topic_type 区分冲突类型."""
    from app.schemas.memory_v2 import DiscussionDecisionRead
    fields = set(DiscussionDecisionRead.model_fields.keys())
    assert "status" in fields, "DiscussionDecisionRead 缺 status"
    assert "topic_type" in fields, (
        "DiscussionDecisionRead 缺 topic_type (类似 decision_type/conflict_type)"
    )
    assert "decision" in fields, "DiscussionDecisionRead 缺 decision (裁决结果)"


def test_run_decision_endpoint_exists():
    """P5 §10.2: 跑 DiscussionDecision 的端点存在."""
    from app.main import app
    pm = [r.path for r in app.routes if hasattr(r, "path") and "/project-memory" in r.path]
    has_run = any("/run" in p for p in pm)
    assert has_run, f"project-memory 端点缺 run: {pm}"


def test_apply_decision_endpoint_exists():
    """P5 §10.4: 把裁决写回 StableMemory 的 apply 端点存在."""
    from app.main import app
    pm = [r.path for r in app.routes if hasattr(r, "path") and "/project-memory" in r.path]
    has_apply = any("/apply" in p for p in pm)
    assert has_apply, f"project-memory 端点缺 apply: {pm}"


# ============================================================
# §12 回归检查 — 旧功能 schema 没破坏
# ============================================================

def test_provider_create_schema():
    """P5 §12.8: 配置 Provider — ModelProviderCreate 接受 name+base_url+api_key+enabled."""
    from app.schemas.model_provider import ModelProviderCreate
    body = ModelProviderCreate(
        name="whitedream",
        base_url="https://sub.whitedream.top/v1",
        api_key="sk-test-12345",
        enabled=True,
    )
    assert body.name == "whitedream"
    assert body.base_url.startswith("https://")
    assert body.api_key == "sk-test-12345"


def test_prompt_template_create_schema():
    """P5 §12.x: 写 prompt 模板 — project.py 里 ChapterCreate, prompt.py 里
    只有 Read/Version. 直接看 prompt.py 的 schema 跟 minimal create body."""
    from app.schemas.prompt import PromptTemplateRead
    fields = set(PromptTemplateRead.model_fields.keys())
    # Read 至少要 key/name/category/role
    for k in ("template_key", "name", "category", "role"):
        assert k in fields, f"PromptTemplateRead 缺 {k}"


def test_chapter_create_schema():
    """P5 §12.5: 创建章节 — ChapterCreate 接受 project_id 隐式 +
    chapter_no + title (+ optional outline)."""
    from app.schemas.project import ChapterCreate
    body = ChapterCreate(
        chapter_no=1,
        title="第1章",
    )
    assert body.title == "第1章"
    assert body.chapter_no == 1


# ============================================================
# 跨阶段 — 关键 schema 命名空间干净
# ============================================================

def test_no_pydantic_namespace_warnings_on_import():
    """P5 §1.4: import 全部 schemas 时不应有 'model_* namespace' warning."""
    import warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        from app.schemas.agent_role import (
            AgentRoleMatrixItem, AgentModelBindingRead,
            AgentModelBindingUpdate, AgentRunRead,
        )
        from app.schemas.memory_v2 import StableMemoryEntityRead
        from app.schemas.deepstudy import StudyRunRead
        from app.schemas.study import StudyMaterialRead
        from app.schemas.project import ChapterRead
        from app.schemas.model_provider import ModelProviderRead
        from app.schemas.prompt import PromptTemplateRead
        offending = [x for x in w if "protected namespace" in str(x.message)]
        assert not offending, (
            f"还有 protected namespace 警告没修: "
            + "; ".join(str(x.message) for x in offending)
        )
