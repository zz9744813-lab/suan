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
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # --- database ---
    # SQLite is the default for local dev; switch to postgresql+psycopg later
    database_url: str = f"sqlite+aiosqlite:///{DATA_DIR / 'novelforge.db'}"

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
