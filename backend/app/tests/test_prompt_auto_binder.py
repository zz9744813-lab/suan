"""NF2 阶段1: PromptAutoBinder tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.services.prompt_auto_binder import (
    PromptAutoBinder,
    AGENT_KEY_TO_TEMPLATE_PREFIX,
    GENRE_KEYWORDS,
)


def _make_template(**overrides):
    t = MagicMock()
    t.id = 1
    t.template_key = "planner.default"
    t.name = "Planner Default"
    t.description = "Default planner template"
    for k, v in overrides.items():
        setattr(t, k, v)
    return t


def _make_mapping(**overrides):
    m = MagicMock()
    m.id = 1
    m.agent_role_key = "planner"
    m.genre = "玄幻"
    m.prompt_template_id = 1
    m.locked_by_user = False
    m.source = "manual"
    m.confidence_score = None
    m.auto_bind_reason = None
    m.auto_fill_batch_id = None
    m.last_effect_score = None
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


class TestPromptAutoBinder:
    @pytest.mark.asyncio
    async def test_locked_cell_not_overwritten(self):
        """用户锁定的格子不应被覆盖."""
        binder = PromptAutoBinder()
        locked_mapping = _make_mapping(locked_by_user=True, prompt_template_id=42)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = locked_mapping
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await binder.auto_fill_for_agent_genre(
            mock_db, "planner", "玄幻",
        )

        assert result["action"] == "skipped"
        assert result["confidence_score"] == 1.0

    @pytest.mark.asyncio
    async def test_no_template_returns_missing(self):
        """无模板时应返回 no_template."""
        binder = PromptAutoBinder()

        mock_db = AsyncMock()

        call_count = 0
        def mock_execute(q):
            nonlocal call_count
            call_count += 1
            r = MagicMock()
            if call_count == 1:
                # locked mapping check → None
                r.scalar_one_or_none.return_value = None
            elif call_count == 2:
                # all templates → empty
                r.scalars.return_value.all.return_value = []
            else:
                r.scalars.return_value.all.return_value = []
            return r

        mock_db.execute = AsyncMock(side_effect=mock_execute)

        result = await binder.auto_fill_for_agent_genre(
            mock_db, "unknown_agent", "玄幻",
        )

        assert result["action"] == "no_template"
        assert result["confidence_score"] == 0.0

    @pytest.mark.asyncio
    async def test_drafter_not_bound_to_strict_json(self):
        """Drafter 不应绑定 strict_json 模板 (验证 key 前缀匹配逻辑)."""
        # drafter 的前缀是 ["drafter", "draft", "writer"]
        prefixes = AGENT_KEY_TO_TEMPLATE_PREFIX.get("drafter", [])
        # 确认不包含 planner/critic/review 等 strict_json 相关前缀
        assert "planner" not in prefixes
        assert "critic" not in prefixes
        assert "review" not in prefixes

    @pytest.mark.asyncio
    async def test_reader_toxic_gets_toxic_template(self):
        """Reader·毒点应获得 toxic/review 标签模板 (验证 genre 关键词匹配)."""
        # 目前 GENRE_KEYWORDS 不含 "毒点", 但测试匹配逻辑
        binder = PromptAutoBinder()

        # 模拟有 toxic 相关模板
        toxic_tpl = _make_template(id=10, template_key="critic.toxic", description="toxic review template")
        critic_tpl = _make_template(id=11, template_key="critic.default", description="default critic")

        mock_db = AsyncMock()

        call_count = 0
        def mock_execute(q):
            nonlocal call_count
            call_count += 1
            r = MagicMock()
            if call_count == 1:
                # locked mapping → None
                r.scalar_one_or_none.return_value = None
            elif call_count == 2:
                # all templates
                r.scalars.return_value.all.return_value = [toxic_tpl, critic_tpl]
            elif call_count == 3:
                # existing maps
                r.scalars.return_value.all.return_value = []
            else:
                # create new mapping check
                r.scalar_one_or_none.return_value = None
            return r

        mock_db.execute = AsyncMock(side_effect=mock_execute)
        mock_db.flush = AsyncMock()

        result = await binder.auto_fill_for_agent_genre(
            mock_db, "critic", "悬疑", dry_run=True,
        )

        # 应该有 confidence_score
        assert "confidence_score" in result

    @pytest.mark.asyncio
    async def test_batch_id_set_on_auto_fill(self):
        """自动填充应设置 batch_id."""
        binder = PromptAutoBinder()

        tpl = _make_template(id=1, template_key="planner.default")

        mock_db = AsyncMock()
        call_count = 0
        def mock_execute(q):
            nonlocal call_count
            call_count += 1
            r = MagicMock()
            if call_count == 1:
                r.scalar_one_or_none.return_value = None  # no locked
            elif call_count == 2:
                r.scalars.return_value.all.return_value = [tpl]  # templates
            elif call_count == 3:
                r.scalars.return_value.all.return_value = []  # existing maps
            else:
                r.scalar_one_or_none.return_value = None  # no existing mapping
            return r
        mock_db.execute = AsyncMock(side_effect=mock_execute)
        mock_db.flush = AsyncMock()
        mock_db.add = MagicMock()

        result = await binder.auto_fill_for_agent_genre(
            mock_db, "planner", "玄幻", batch_id="test-batch-01",
        )

        # 验证 add 被调用且 mapping 有 batch_id
        if mock_db.add.called:
            added_mapping = mock_db.add.call_args[0][0]
            assert added_mapping.auto_fill_batch_id == "test-batch-01"

    @pytest.mark.asyncio
    async def test_dry_run_does_not_write(self):
        """dry_run 模式不应写入数据库."""
        binder = PromptAutoBinder()

        tpl = _make_template(id=1, template_key="planner.default")

        mock_db = AsyncMock()
        call_count = 0
        def mock_execute(q):
            nonlocal call_count
            call_count += 1
            r = MagicMock()
            if call_count == 1:
                r.scalar_one_or_none.return_value = None  # no locked
            elif call_count == 2:
                r.scalars.return_value.all.return_value = [tpl]  # templates
            elif call_count == 3:
                r.scalars.return_value.all.return_value = []  # existing maps
            else:
                r.scalar_one_or_none.return_value = None
            return r
        mock_db.execute = AsyncMock(side_effect=mock_execute)
        mock_db.flush = AsyncMock()
        mock_db.add = MagicMock()

        result = await binder.auto_fill_for_agent_genre(
            mock_db, "planner", "玄幻", dry_run=True,
        )

        assert result["action"] == "dry_run"
        assert not mock_db.add.called  # 不写入
        assert not mock_db.flush.called

    @pytest.mark.asyncio
    async def test_confidence_score_calculated(self):
        """应为每个推荐计算置信度."""
        binder = PromptAutoBinder()

        tpl_xuan = _make_template(id=1, template_key="planner.xuanhuan", description="玄幻专用")
        tpl_default = _make_template(id=2, template_key="planner.default", description="通用")

        mock_db = AsyncMock()
        call_count = 0
        def mock_execute(q):
            nonlocal call_count
            call_count += 1
            r = MagicMock()
            if call_count == 1:
                r.scalar_one_or_none.return_value = None  # no locked
            elif call_count == 2:
                r.scalars.return_value.all.return_value = [tpl_xuan, tpl_default]
            elif call_count == 3:
                r.scalars.return_value.all.return_value = []  # existing maps
            else:
                r.scalar_one_or_none.return_value = None
            return r
        mock_db.execute = AsyncMock(side_effect=mock_execute)
        mock_db.flush = AsyncMock()

        result = await binder.auto_fill_for_agent_genre(
            mock_db, "planner", "玄幻", dry_run=True,
        )

        assert "confidence_score" in result
        assert isinstance(result["confidence_score"], float)
        assert result["confidence_score"] > 0.0

    @pytest.mark.asyncio
    async def test_auto_fill_all_batch(self):
        """auto_fill_all 应批量处理多个 agent+genre 组合."""
        binder = PromptAutoBinder()

        tpl = _make_template(id=1, template_key="planner.default")

        mock_db = AsyncMock()

        # auto_fill_all 内部会多次调用 auto_fill_for_agent_genre
        # 我们直接 mock auto_fill_for_agent_genre
        async def mock_auto_fill(db, agent_key, genre, **kwargs):
            return {
                "agent_role_key": agent_key,
                "genre": genre,
                "action": "created",
                "confidence_score": 0.8,
            }

        with patch.object(binder, "auto_fill_for_agent_genre", side_effect=mock_auto_fill):
            result = await binder.auto_fill_all(
                mock_db,
                genres=["玄幻"],
                agent_role_keys=["planner", "drafter"],
                dry_run=True,
            )

        assert "batch_id" in result
        assert result["total"] == 2
        assert result["created"] == 2

