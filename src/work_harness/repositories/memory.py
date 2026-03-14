from __future__ import annotations

from collections import defaultdict
from typing import Any

from work_harness.domain.models import ExecutionRun, WorkItem


class InMemoryWorkItemRepository:
    def __init__(self) -> None:
        self._items: dict[str, WorkItem] = {}

    async def upsert(self, item: WorkItem) -> WorkItem:
        self._items[item.id] = item
        return item

    async def get(self, item_id: str) -> WorkItem | None:
        return self._items.get(item_id)

    async def list(self) -> list[WorkItem]:
        return list(self._items.values())


class InMemoryRunRepository:
    def __init__(self) -> None:
        self._runs: dict[str, ExecutionRun] = {}
        self._events: dict[str, list[dict[str, Any]]] = defaultdict(list)

    async def upsert(self, run: ExecutionRun) -> ExecutionRun:
        self._runs[run.thread_id] = run
        self._events[run.thread_id].extend(run.events)
        return run

    async def get(self, thread_id: str) -> ExecutionRun | None:
        return self._runs.get(thread_id)

    async def append_event(self, thread_id: str, event: dict[str, Any]) -> None:
        self._events[thread_id].append(event)
        run = self._runs.get(thread_id)
        if run:
            run.events.append(event)

    async def get_events(self, thread_id: str) -> list[dict[str, Any]]:
        return list(self._events.get(thread_id, []))

