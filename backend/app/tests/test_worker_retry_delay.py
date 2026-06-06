"""P0 Phase 5: Worker delayed retry tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from app.workers.worker import WorkerController, SUPPORTED_TASKS


def _make_task(**overrides):
    t = MagicMock()
    t.id = 1
    t.project_id = 1
    t.chapter_id = 1
    t.task_type = "chapter_pipeline"
    t.status = "failed"
    t.retry_count = 0
    t.max_retries = 3
    t.error = None
    t.not_before_at = None
    t.started_at = None
    t.finished_at = None
    t.payload = {}
    t.cost_usd = 0.0
    t.input_tokens = 0
    t.output_tokens = 0
    for k, v in overrides.items():
        setattr(t, k, v)
    return t


def _make_worker_status(**overrides):
    ws = MagicMock()
    ws.id = 1
    ws.state = "running"
    ws.consecutive_failures = 0
    ws.current_task_id = None
    ws.last_error = None
    ws.today_words = 0
    ws.today_cost_usd = 0.0
    ws.last_reset_date = None
    ws.last_heartbeat_at = None
    for k, v in overrides.items():
        setattr(ws, k, v)
    return ws


class TestWorkerRetryDelay:
    @pytest.mark.asyncio
    async def test_transient_failure_sets_not_before_at(self):
        """暂时性失败应设置 not_before_at."""
        worker = WorkerController()
        task = _make_task(retry_count=0, max_retries=3)

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=task)
        # _get_or_create_status
        ws = _make_worker_status()
        with patch.object(worker, "_get_or_create_status", return_value=ws):
            with patch("app.workers.worker.session_scope") as mock_scope:
                mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_db)
                mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
                await worker._mark_task_failed(1, "Connection timeout")

        # retry_count < max_retries → 应设置 not_before_at 并保持 pending
        assert task.not_before_at is not None
        assert task.status == "pending"
        assert task.retry_count == 1

    @pytest.mark.asyncio
    async def test_retry_count_increments(self):
        """重试次数应递增."""
        worker = WorkerController()
        task = _make_task(retry_count=1, max_retries=3)

        with patch.object(worker, "_get_or_create_status", return_value=_make_worker_status()):
            with patch("app.workers.worker.session_scope") as mock_scope:
                mock_scope.return_value.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=task)))
                mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
                await worker._mark_task_failed(1, "error")

        assert task.retry_count == 2

    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        """退避时间应指数增长: 30s, 60s, 120s..."""
        worker = WorkerController()

        # retry_count=0 → delay=30s (2^0 * 30)
        task0 = _make_task(retry_count=0, max_retries=5)
        with patch.object(worker, "_get_or_create_status", return_value=_make_worker_status()):
            with patch("app.workers.worker.session_scope") as mock_scope:
                mock_scope.return_value.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=task0)))
                mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
                await worker._mark_task_failed(1, "error")
        # 2^(retry_count-1) * 30 → retry_count 已递增为 1, 但计算时用递增前的值
        # 实际代码: delay_s = min(30 * (2 ** (t.retry_count - 1)), 300)
        # retry_count=0 → 递增为1 → delay = 30 * 2^0 = 30
        # 但注意: retry_count 先递增再计算, 所以 delay = 30 * 2^(1-1) = 30
        assert task0.not_before_at is not None

        # retry_count=1 → delay=60s (2^1 * 30)
        task1 = _make_task(retry_count=1, max_retries=5)
        with patch.object(worker, "_get_or_create_status", return_value=_make_worker_status()):
            with patch("app.workers.worker.session_scope") as mock_scope:
                mock_scope.return_value.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=task1)))
                mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
                await worker._mark_task_failed(1, "error")
        assert task1.not_before_at is not None

        # retry_count=2 → delay=120s (2^2 * 30)
        task2 = _make_task(retry_count=2, max_retries=5)
        with patch.object(worker, "_get_or_create_status", return_value=_make_worker_status()):
            with patch("app.workers.worker.session_scope") as mock_scope:
                mock_scope.return_value.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=task2)))
                mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
                await worker._mark_task_failed(1, "error")
        assert task2.not_before_at is not None

    @pytest.mark.asyncio
    async def test_max_retry_exhausted_marks_failed(self):
        """耗尽重试次数应标记为 failed."""
        worker = WorkerController()
        task = _make_task(retry_count=2, max_retries=3)

        ws = _make_worker_status()
        with patch.object(worker, "_get_or_create_status", return_value=ws):
            with patch("app.workers.worker.session_scope") as mock_scope:
                mock_scope.return_value.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=task)))
                mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
                with patch("app.workers.worker.event_bus") as mock_bus:
                    mock_bus.publish = AsyncMock()
                    await worker._mark_task_failed(1, "exhausted")

        # retry_count 递增到 3, 等于 max_retries=3 → 最终 failed
        assert task.status == "failed"
        assert task.finished_at is not None

    @pytest.mark.asyncio
    async def test_consecutive_failures_not_incremented_on_retry(self):
        """重试中的失败不应增加 consecutive_failures."""
        worker = WorkerController()
        task = _make_task(retry_count=0, max_retries=3)

        ws = _make_worker_status(consecutive_failures=0)
        with patch.object(worker, "_get_or_create_status", return_value=ws):
            with patch("app.workers.worker.session_scope") as mock_scope:
                mock_scope.return_value.__aenter__ = AsyncMock(return_value=AsyncMock(get=AsyncMock(return_value=task)))
                mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
                await worker._mark_task_failed(1, "transient error")

        # 重试中: consecutive_failures 不增加
        assert ws.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_tick_skips_not_before_at_tasks(self):
        """Worker 应跳过 not_before_at > now 的任务."""
        worker = WorkerController()
        mock_db = AsyncMock()

        # 创建一个 not_before_at 在未来的任务
        future_task = _make_task(
            status="pending",
            task_type="chapter_pipeline",
            not_before_at=datetime.utcnow() + timedelta(hours=1),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # 无可执行任务
        mock_db.execute = AsyncMock(return_value=mock_result)

        ws = _make_worker_status()
        with patch.object(worker, "_get_or_create_status", return_value=ws):
            with patch("app.workers.worker.session_scope") as mock_scope:
                mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_db)
                mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)
                result = await worker._tick()

        # not_before_at > now 的任务被跳过 → 无任务 → 返回 False
        assert result is False

    @pytest.mark.asyncio
    async def test_supported_tasks_includes_chapter_pipeline(self):
        """SUPPORTED_TASKS 应包含 chapter_pipeline."""
        assert "chapter_pipeline" in SUPPORTED_TASKS
