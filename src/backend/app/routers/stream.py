"""
app/routers/stream.py — Server-Sent Events stream.

Gated behind FEATURE_SSE=true (default: false).
If SSE is disabled, the endpoint returns 503 with a clear message.

When enabled, pushes:
  - new_excursion: when a new excursion is detected or severity escalates
  - new_impact: when a shipment is newly impacted by a disruption
  - disruption_resolved: when a disruption closes

For the demo, the replay harness emits events here directly.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings

router = APIRouter(prefix="/stream", tags=["stream"])

# In-memory event queue — populated by replay harness and ingest endpoints
_event_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)


def emit_event(event_type: str, data: dict) -> None:
    """Push an event onto the stream queue (non-blocking)."""
    try:
        _event_queue.put_nowait({
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except asyncio.QueueFull:
        pass  # Drop event if queue is full; stream consumers are optional


if settings.feature_sse:
    try:
        from sse_starlette.sse import EventSourceResponse

        @router.get("/events")
        async def stream_events(request):
            """
            SSE stream of real-time events.
            Enabled when FEATURE_SSE=true.

            Event types:
              - new_excursion
              - new_impact
              - disruption_resolved
              - heartbeat (every 30s)
            """
            async def generator():
                heartbeat_interval = 30  # seconds
                last_hb = asyncio.get_event_loop().time()

                while True:
                    if await request.is_disconnected():
                        break

                    # Drain available events
                    try:
                        event = _event_queue.get_nowait()
                        yield {
                            "event": event["type"],
                            "data": json.dumps(event["data"]),
                        }
                        continue
                    except asyncio.QueueEmpty:
                        pass

                    # Heartbeat
                    now = asyncio.get_event_loop().time()
                    if now - last_hb > heartbeat_interval:
                        yield {
                            "event": "heartbeat",
                            "data": json.dumps({"ts": datetime.now(timezone.utc).isoformat()}),
                        }
                        last_hb = now

                    await asyncio.sleep(1)

            return EventSourceResponse(generator())

    except ImportError:
        # sse_starlette not installed — disable SSE gracefully
        pass

else:
    @router.get("/events")
    async def stream_events_disabled():
        return JSONResponse(
            status_code=503,
            content={
                "detail": "SSE stream is disabled. Set FEATURE_SSE=true to enable.",
                "polling_alternative": "/api/v1/priority-queue supports ?since= for polling.",
            },
        )
