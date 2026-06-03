"""In-process event bus + SSE broadcaster.

The bus is intentionally simple for the local MVP. It serializes events to
JSON and fans them out to per-subscriber asyncio queues. The SSE endpoint
drains a queue and emits `event:` lines for the browser EventSource API.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Event:
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> dict[str, Any]:
        d = {"event_type": self.event_type, "ts": self.ts, **self.payload}
        return d


class EventBus:
    """Fan-out broadcaster for SSE subscribers."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._lock = asyncio.Lock()
        self._history: list[Event] = []
        self._history_max = 500

    async def publish(self, event: Event) -> None:
        self._history.append(event)
        if len(self._history) > self._history_max:
            self._history = self._history[-self._history_max :]
        async with self._lock:
            dead: list[asyncio.Queue[Event]] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    dead.append(q)
            for q in dead:
                self._subscribers.discard(q)

    def publish_sync(self, event: Event) -> None:
        """Schedule publish on the running loop without awaiting."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.publish(event))

    async def subscribe(self) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=200)
        async with self._lock:
            self._subscribers.add(q)
        # replay recent history so new clients catch up
        for ev in self._history[-50:]:
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:
                break
        return q

    async def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        async with self._lock:
            self._subscribers.discard(q)

    def recent(self, limit: int = 50) -> list[Event]:
        return self._history[-limit:]


event_bus = EventBus()


def sse_format(event: Event) -> str:
    """Format an Event as a Server-Sent-Events frame."""
    data = json.dumps(event.to_dict(), ensure_ascii=False, default=str)
    return f"event: {event.event_type}\ndata: {data}\n\n"


async def sse_stream() -> AsyncIterator[Event]:
    """Async generator yielding events for an SSE endpoint."""
    q = await event_bus.subscribe()
    try:
        # initial ping so the browser EventSource flips to OPEN
        yield Event(event_type="sse.connected", payload={})
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), timeout=15.0)
                yield ev
            except asyncio.TimeoutError:
                # heartbeat keeps proxies from severing the connection
                yield Event(event_type="sse.heartbeat", payload={})
    finally:
        await event_bus.unsubscribe(q)
