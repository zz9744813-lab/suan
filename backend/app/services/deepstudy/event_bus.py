"""Simple async event bus for DeepStudy stage lifecycle events.

Stage completions are published so that downstream services
(graph materializer, behaviour miner, etc.) can auto-link
outputs without the coordinator having to know about every
consumer.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Callable

Callback = Callable[..., Any]


class DeepStudyEventBus:
    """Lightweight pub/sub for DeepStudy stage events.

    Listeners register for event types (e.g. "stage_completed",
    "run_failed", "run_succeeded") and are called when the
    coordinator publishes those events.

    This is intentionally in-process (no Redis / Kafka) — the
    coordinator runs single-threaded per material and the bus
    exists to decouple the coordinator from the materialiser /
    miner / indexer layers.
    """

    def __init__(self) -> None:
        self.listeners: dict[str, list[Callback]] = defaultdict(list)

    async def publish(
        self,
        event_type: str,
        material_id: int,
        run_id: int,
        stage_key: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Notify all listeners registered for ``event_type``.

        Each listener is called concurrently; failures in one
        listener do not prevent others from running.
        """
        callbacks = self.listeners.get(event_type, [])
        if not callbacks:
            return

        coros: list[Any] = []
        for cb in callbacks:
            try:
                result = cb(
                    event_type=event_type,
                    material_id=material_id,
                    run_id=run_id,
                    stage_key=stage_key,
                    payload=payload or {},
                )
                if asyncio.iscoroutine(result):
                    coros.append(result)
            except Exception:
                # Swallow per-listener errors so one bad subscriber
                # doesn't break the entire pipeline.
                pass

        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    def subscribe(self, event_type: str, callback: Callback) -> None:
        """Register a listener for ``event_type``.

        The callback receives keyword arguments:
            event_type, material_id, run_id, stage_key, payload
        """
        self.listeners[event_type].append(callback)

    async def stage_completed(
        self,
        material_id: int,
        run_id: int,
        stage_key: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Convenience: publish a ``stage_completed`` event."""
        await self.publish(
            event_type="stage_completed",
            material_id=material_id,
            run_id=run_id,
            stage_key=stage_key,
            payload=payload or {},
        )


# Global singleton — one bus per process.
deepstudy_event_bus = DeepStudyEventBus()
