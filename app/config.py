"""全局配置（pydantic-settings）。

对应工程方案：
- 第 41 节 LLM Provider 架构
- 第 42 节 模型分层
- 第 4 节 Prediction Budget
- 第 58 节 Scheduler
- 第 64 节 隐私
- 第 34 / 35 节 实验模式
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderSettings(BaseSettings):
    """单个 LLM Provider 的连接配置。第 41 节。"""

    base_url: str = ""
    api_key: str = ""
    model: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------- 应用 ----------
    XUANMIRROR_ENV: Literal["dev", "test", "prod"] = "dev"
    XUANMIRROR_DEBUG: bool = True
    XUANMIRROR_DB_URL: str = "sqlite:///./data/xuanmirror.db"
    XUANMIRROR_TIMEZONE: str = "Asia/Shanghai"

    # ---------- 模型分层（第 42 节）----------
    # Rule Calculation      → 程序，无 LLM
    # Signal Formatting     → CHEAP
    # Outcome Parsing       → CHEAP
    # Specialist Interp.    → REASONING（中高）
    # Fusion                → REASONING（强推理）
    # Adversarial Review    → REASONING（独立强推理）
    # Monthly Audit         → REASONING（强推理）
    REASONING_BASE_URL: str = ""
    REASONING_API_KEY: str = ""
    REASONING_MODEL: str = ""

    CHEAP_BASE_URL: str = ""
    CHEAP_API_KEY: str = ""
    CHEAP_MODEL: str = ""

    VISION_BASE_URL: str = ""
    VISION_API_KEY: str = ""
    VISION_MODEL: str = ""

    # ---------- 调度（第 58 节）----------
    SCHEDULER_ENABLED: bool = False
    SCHEDULER_REALITY_UPDATE: str = "23:30"
    SCHEDULER_FUTURE_SCAN: str = "23:40"
    SCHEDULER_METAPHYSICAL: str = "23:45"
    SCHEDULER_AGENT_REVIEW: str = "23:50"
    SCHEDULER_FREEZE: str = "23:55"

    # ---------- Prediction Budget（第 4 节）----------
    # 强制下注制度：禁止撒网式算准。
    BUDGET_TOMORROW_STRONG: int = 5
    BUDGET_TOMORROW_WATCH: int = 5
    BUDGET_7D: int = 5
    BUDGET_30D: int = 5
    BUDGET_90D: int = 3

    # ---------- 隐私（第 64 节）----------
    # 面部、掌纹、出生信息属于高敏感个人数据，本地优先。
    ENABLE_CLOUD_VISION: bool = False
    PRE_UPLOAD_CROP: bool = True

    # ---------- 实验模式（第 34 / 35 节）----------
    # "" = 正常 | blind_ab = 双盲对照 | hidden = 隐藏预测防自我实现
    EXPERIMENT_MODE: str = ""

    # ---------- 版本标识（第 79 节模型版本管理）----------
    MODEL_VERSION: str = "fusion-0.1.0"
    FUSION_VERSION: str = "fusion-0.1.0"
    PROMPT_VERSION: str = "prompt-0.1.0"
    RULE_VERSION: str = "rules-0.1.0"
    ENGINE_VERSION: str = "engines-0.1.0"

    # ---------- 小样本保护（第 78 节）----------
    # 不能 3 次预测 3 次成功就宣布 100% 准确。
    MIN_SAMPLE_FOR_RELIABILITY: int = 20
    PRIOR_STRENGTH: float = Field(default=10.0, ge=0.0)

    # ---------- 预测质量门槛（C-006 诚实原则）----------
    # 融合概率与 Null 基线的差距（edge = p - null）绝对值小于此阈值时，
    # 说明术数/现实信号没有提供超出随机的信息，候选会被诚实拒绝（NO_EDGE），
    # 不进入正式冻结账本，避免产出「贴 Null 的噪声预测」误导用户。
    # 实测纯术式噪声的 |edge| 分布约 0.44~2.36pp，故默认 3pp 可滤除全部纯噪声；
    # 未来积累真实样本后，有预测力的信号 edge 会显著超过此阈值，自动放行。
    MIN_PREDICTION_EDGE: float = Field(default=0.03, ge=0.0, le=0.5)

    # ---------- 派生 ----------
    def provider(self, tier: Literal["reasoning", "cheap", "vision"]) -> ProviderSettings:
        """按分层取 Provider 配置。"""
        prefix = tier.upper()
        return ProviderSettings(
            base_url=getattr(self, f"{prefix}_BASE_URL", ""),
            api_key=getattr(self, f"{prefix}_API_KEY", ""),
            model=getattr(self, f"{prefix}_MODEL", ""),
        )

    @property
    def budget_table(self) -> dict[str, int]:
        """第 4.2 节强制下注制度。"""
        return {
            "tomorrow_strong": self.BUDGET_TOMORROW_STRONG,
            "tomorrow_watch": self.BUDGET_TOMORROW_WATCH,
            "7d": self.BUDGET_7D,
            "30d": self.BUDGET_30D,
            "90d": self.BUDGET_90D,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
