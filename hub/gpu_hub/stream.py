"""Server-sent-events fan-out for the dashboard.

A single ticker serialises the cluster state once per interval and hands the same string
to every connected browser, rather than each connection re-serialising on its own timer.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from .state import Store

log = logging.getLogger(__name__)

# Deliberately small: if a client cannot keep up with 1 Hz it should drop frames rather
# than accumulate a backlog of stale GPU readings.
_QUEUE_SIZE = 2


class Broadcaster:
    def __init__(self, store: Store, interval: float) -> None:
        self._store = store
        self._interval = interval
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="sse-ticker")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def snapshot_json(self) -> str:
        return self._store.cluster_state().model_dump_json()

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            if not self._subscribers:
                continue
            try:
                payload = self.snapshot_json()
            except Exception:
                log.exception("failed to serialise cluster state")
                continue
            for queue in list(self._subscribers):
                if queue.full():
                    with contextlib.suppress(asyncio.QueueEmpty):
                        queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(payload)

    async def events(self) -> AsyncIterator[str]:
        """Yield raw SSE frames for one connection until the client goes away."""
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_QUEUE_SIZE)
        self._subscribers.add(queue)
        try:
            # Tell the browser how fast to reconnect, then send the current state
            # immediately so the dashboard is never blank for a whole interval.
            yield "retry: 2000\n\n"
            yield _frame(self.snapshot_json())
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # Comment frame: keeps idle connections alive through proxies and
                    # tunnels that would otherwise time them out.
                    yield ": keepalive\n\n"
                    continue
                yield _frame(payload)
        finally:
            self._subscribers.discard(queue)


def _frame(payload: str) -> str:
    return f"event: state\ndata: {payload}\n\n"
