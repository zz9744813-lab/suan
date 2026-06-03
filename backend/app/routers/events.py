"""SSE event stream for the live event timeline."""
from __future__ import annotations

import json

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.core.events import sse_stream


router = APIRouter(prefix="/events", tags=["events"])


@router.get("/stream")
async def stream():
    async def event_generator():
        async for ev in sse_stream():
            yield {
                "event": ev.event_type,
                "data": json.dumps(ev.to_dict(), ensure_ascii=False, default=str),
            }

    return EventSourceResponse(event_generator())
