"""Application configuration."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BACKEND_DIR / "data"


class Settings(BaseSettings):
    """Runtime configuration loaded from environment or .env file."""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- app ---
    app_name: str = "NovelForge 2.0"
    app_version: str = "0.1.0"
    debug: bool = True
    api_prefix: str = "/api"

    # --- server ---
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173", "http://127.0.0.1:5173",
            "http://localhost:5174", "http://127.0.0.1:5174",
        ]
    )

    # --- database ---
    # 阶段 3.1: 默认数据库已切换为 PostgreSQL.
    # - 生产: postgresql+asyncpg://user:pass@host:5432/db
    # - dev 仍可用 SQLite 回归: sqlite+aiosqlite:///./data/novelforge.db
    # 真正在 engine 上挂 SQLite 兼容逻辑在 3.2 阶段处理, 3.1 仅改默认.
    default_database_url: str = f"sqlite+aiosqlite:///{DATA_DIR / 'novelforge.db'}"
    database_url: str = default_database_url
    # 切换提示: 部署前请覆盖 database_url 为 postgresql+asyncpg://...

    # --- redis / queue (阶段 3.1) ---
    redis_url: str = "redis://127.0.0.1:6379/0"
    # Worker 进程并发数, 与 arq 的 max_jobs 不同: 这是同一进程内可同时
    # 领取的任务数; max_jobs 是单进程总上限. 一般 max_jobs = concurrency * 2.
    worker_concurrency: int = 4
    worker_max_jobs: int = 8
    # 任务在队列里最多存活多久 (秒). 超过会被 DLQ 接管.
    task_default_ttl_seconds: int = 3600
    # 单任务最大重试次数, 写回 agent_tasks.max_retries.
    task_max_retries: int = 3
    # 是否在 API 进程内继续跑 Worker.
    # 阶段 3.6 起: 默认 False. API 只入队, 由独立 backend-worker (arq) 消费.
    # 仍允许通过 .env 覆盖到 True (仅用于本地 SQLite 回归, 不要用于生产).
    worker_run_in_process: bool = False

    # --- auth ---
    api_key: str = "novelforge-local-dev-key"  # set NOVELFORGE_API_KEY in prod

    # --- worker ---
    worker_idle_poll_seconds: float = 1.0
    worker_heartbeat_seconds: float = 5.0

    # --- llm ---
    # Single read timeout used for the chat-completions POST. We split
    # connect / pool / write into a small value below to fail fast on
    # unreachable hosts, but give the LLM plenty of headroom to stream a
    # 2-4K-token reply on slow providers.
    llm_default_timeout_seconds: float = 600.0
    # 2 retries keeps the per-agent worst case at ~20 minutes (2 * 600s)
    # instead of 36 minutes with the previous 3-retry * 120s setting.
    llm_max_retries: int = 2
    # Fast-fail for the TCP / TLS handshake. If we cannot reach the
    # provider within this many seconds, surface a clear error instead
    # of burning the full read budget on a stuck connection.
    llm_connect_timeout_seconds: float = 15.0

    # --- agent defaults ---
    default_pass_score: int = 80
    default_max_rewrite_rounds: int = 2
    default_daily_word_goal: int = 30000
    default_daily_budget_usd: float = 8.0

    # --- storage ---
    storage_dir: Path = DATA_DIR / "storage"
    log_dir: Path = DATA_DIR / "logs"

    def ensure_dirs(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
