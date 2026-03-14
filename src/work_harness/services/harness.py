from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from work_harness.connectors.base import ConnectorAdapter
from work_harness.domain.models import (
    ActivityEvent,
    AnalysisRecord,
    ConnectorSource,
    DecisionPayload,
    DecisionType,
    ExecutionRun,
    GraphResult,
    RunStatus,
    WorkItem,
    WorkItemStatus,
)
from work_harness.graph.supervisor import SupervisorService
from work_harness.repositories.memory import InMemoryRunRepository, InMemoryWorkItemRepository
from work_harness.services.audit_log import AuditLog
from work_harness.services.knowledge_store import KnowledgeStore


class RunEventBus:
    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, thread_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._queues.setdefault(thread_id, []).append(queue)
        return queue

    async def publish(self, thread_id: str, event: dict[str, Any]) -> None:
        for queue in self._queues.get(thread_id, []):
            await queue.put(event)

    def unsubscribe(self, thread_id: str, queue: asyncio.Queue) -> None:
        subscribers = self._queues.get(thread_id, [])
        if queue in subscribers:
            subscribers.remove(queue)


class HarnessService:
    def __init__(
        self,
        supervisor: SupervisorService,
        connectors: dict[ConnectorSource, ConnectorAdapter],
        knowledge_store: KnowledgeStore,
        audit_log: AuditLog,
    ) -> None:
        self._supervisor = supervisor
        self._connectors = connectors
        self._knowledge_store = knowledge_store
        self._audit_log = audit_log
        self._work_items = InMemoryWorkItemRepository()
        self._runs = InMemoryRunRepository()
        self._bus = RunEventBus()

    async def ingest_event(self, source: ConnectorSource, payload: dict[str, Any]) -> GraphResult:
        connector = self._connectors.get(source)
        if connector:
            event = await connector.handle_webhook(payload)
        else:
            event = ActivityEvent(source=source, **payload)

        result = await self._supervisor.handle_event(event)
        await self._work_items.upsert(result.work_item)
        await self._runs.upsert(result.run)
        await self._knowledge_store.store_analysis(
            AnalysisRecord(
                ticket_key=event.external_id,
                core_issue=result.work_item.proposal.summary,
                keywords=[event.source.value, result.work_item.proposal.recommended_agent],
                summary=result.work_item.proposal.summary,
                final_summary=result.work_item.proposal.suggested_action,
                session_id=result.run.thread_id,
            )
        )
        await self._audit_log.append("work_item.created", result.work_item.model_dump(mode="json"))
        await self._bus.publish(
            result.run.thread_id,
            {"type": "work_item_created", "work_item_id": result.work_item.id},
        )
        return result

    async def list_work_items(self) -> list[WorkItem]:
        items = await self._work_items.list()
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    async def get_work_item(self, item_id: str) -> WorkItem | None:
        return await self._work_items.get(item_id)

    async def decide(self, item_id: str, payload: DecisionPayload) -> WorkItem:
        item = await self._work_items.get(item_id)
        if item is None:
            raise KeyError(item_id)

        status_map = {
            DecisionType.ACCEPT: WorkItemStatus.ACCEPTED,
            DecisionType.REJECT: WorkItemStatus.REJECTED,
            DecisionType.ADVISE: WorkItemStatus.ADVISED,
            DecisionType.DEFER: WorkItemStatus.DEFERRED,
        }
        item.status = status_map[payload.decision]
        item.decision_comment = payload.comment
        item.updated_at = datetime.now(tz=UTC)
        await self._work_items.upsert(item)

        run = await self._runs.get(item.thread_id)
        if run is None:
            run = ExecutionRun(thread_id=item.thread_id, work_item_id=item.id)
        run.current_step = f"decision_{payload.decision.value}"
        run.status = (
            RunStatus.COMPLETED
            if payload.decision != DecisionType.DEFER
            else RunStatus.WAITING
        )
        run.updated_at = datetime.now(tz=UTC)
        event = {"type": "decision", "decision": payload.decision.value, "comment": payload.comment}
        run.events.append(event)
        await self._runs.upsert(run)
        await self._audit_log.append(
            "work_item.decided",
            {"work_item_id": item.id, **payload.model_dump(mode="json")},
        )
        await self._bus.publish(item.thread_id, event)
        return item

    async def get_run(self, thread_id: str) -> ExecutionRun | None:
        return await self._runs.get(thread_id)

    async def get_recent_audit(self, limit: int = 20) -> list[dict[str, Any]]:
        return await self._audit_log.list_recent(limit)

    async def stream_events(self, thread_id: str):
        queue = self._bus.subscribe(thread_id)
        existing = await self._runs.get_events(thread_id)
        try:
            for event in existing:
                yield f"data: {json.dumps(event)}\n\n"
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            self._bus.unsubscribe(thread_id, queue)
