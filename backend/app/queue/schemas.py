"""队列任务体协议 (与 arq 解耦的 dataclass)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentTaskJob:
    task_id: int
    task_type: str
    enqueued_at: str = ""

    @classmethod
    def from_kwargs(cls, kwargs: dict) -> "AgentTaskJob":
        return cls(
            task_id=int(kwargs["task_id"]),
            task_type=str(kwargs["task_type"]),
            enqueued_at=str(kwargs.get("enqueued_at") or ""),
        )
