from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from work_harness.connectors.base import ConnectorAdapter
from work_harness.domain.models import (
    ActivityEvent,
    ConnectorSource,
    DecisionPayload,
    DecisionType,
    ExecutionRun,
    IngressResult,
    RunStatus,
    WorkItem,
    WorkItemStatus,
)
from work_harness.graph.supervisor import SupervisorService
from work_harness.repositories.sqlite import SqliteRunRepository, SqliteWorkItemRepository
from work_harness.services.audit_log import AuditLog
from work_harness.services.settings_service import SettingsService


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


logger = logging.getLogger("work_harness.services.harness")


class HarnessService:
    def __init__(
        self,
        supervisor: SupervisorService,
        connectors: dict[ConnectorSource, ConnectorAdapter],
        audit_log: AuditLog,
        settings_service: SettingsService,
        chat_provider: object | None = None,
        work_items: SqliteWorkItemRepository | None = None,
        runs: SqliteRunRepository | None = None,
    ) -> None:
        self._supervisor = supervisor
        self._connectors = connectors
        self._audit_log = audit_log
        self._settings_service = settings_service
        self._chat_provider = chat_provider
        self._work_items = work_items
        self._runs = runs
        self._bus = RunEventBus()

    async def initialize(self) -> None:
        if self._work_items:
            await self._work_items.initialize()
        if self._runs:
            await self._runs.initialize()

    async def ingest_event(self, source: ConnectorSource, payload: dict[str, Any]) -> IngressResult:
        logger.info("Ingesting event: source=%s", source.value)
        connector = self._connectors.get(source)
        if connector:
            event = await connector.handle_webhook(payload)
        else:
            event = ActivityEvent(source=source, **payload)
        logger.debug(
            "Event parsed: type=%s id=%s actor=%s",
            event.event_type, event.external_id, event.actor,
        )

        should_process, subscription_key, reason = (
            await self._settings_service.should_process_event(source, event)
        )
        if not should_process:
            logger.info(
                "Event skipped: source=%s key=%s reason=%s",
                source.value, subscription_key, reason,
            )
            await self._audit_log.append(
                "work_item.skipped",
                {
                    "source": source.value,
                    "subscription_key": subscription_key,
                    "reason": reason,
                    "external_id": event.external_id,
                },
            )
            return IngressResult(
                processed=False,
                source=source,
                subscription_key=subscription_key,
                reason=reason,
            )

        result = await self._supervisor.handle_event(event)
        await self._work_items.upsert(result.work_item)
        await self._runs.upsert(result.run)
        await self._audit_log.append("work_item.created", result.work_item.model_dump(mode="json"))
        await self._bus.publish(
            result.run.thread_id,
            {"type": "work_item_created", "work_item_id": result.work_item.id},
        )
        logger.info(
            "Work item created: id=%s source=%s key=%s",
            result.work_item.id, source.value, subscription_key,
        )
        return IngressResult(
            processed=True,
            source=source,
            subscription_key=subscription_key,
            reason=reason,
            work_item=result.work_item,
            run=result.run,
        )

    async def list_work_items(self) -> list[WorkItem]:
        items = await self._work_items.list()
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    async def get_work_item(self, item_id: str) -> WorkItem | None:
        return await self._work_items.get(item_id)

    async def decide(self, item_id: str, payload: DecisionPayload) -> WorkItem:
        logger.info("Decision: item_id=%s decision=%s", item_id, payload.decision.value)
        item = await self._work_items.get(item_id)
        if item is None:
            logger.warning("Decision target not found: %s", item_id)
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

        if (
            payload.decision == DecisionType.ACCEPT
            and payload.comment
            and self._chat_provider
            and item.source in self._connectors
        ):
            action_event = await self._execute_steering(
                item, payload.comment,
            )
            item.action_result = action_event
            item.updated_at = datetime.now(tz=UTC)
            await self._work_items.upsert(item)
            run.events.append(action_event)
            run.updated_at = datetime.now(tz=UTC)
            await self._runs.upsert(run)
            await self._bus.publish(item.thread_id, action_event)

        return item

    async def _execute_steering(
        self,
        item: WorkItem,
        comment: str,
    ) -> dict[str, Any]:
        logger.info(
            "Steering: item=%s comment=%s",
            item.id, comment[:80],
        )
        allowed = await self._settings_service.get_allowed_actions(
            item.source,
        )
        if not allowed:
            logger.info(
                "Steering skipped: no allowed actions for %s",
                item.source.value,
            )
            return {
                "type": "steering_skip",
                "reasoning": (
                    f"No actions enabled for {item.source.value}. "
                    "Enable actions in Settings."
                ),
            }

        available_tools = await self._settings_service.get_available_tools(
            item.source,
        )
        usable_tools = [
            t for t in available_tools if str(t["key"]) in allowed
        ]
        if not usable_tools:
            return {
                "type": "steering_skip",
                "reasoning": "No tools available for the current token scopes.",
            }

        repo = ""
        if isinstance(item.metadata, dict):
            repo_meta = item.metadata.get("repository")
            if isinstance(repo_meta, dict):
                repo = str(repo_meta.get("full_name", ""))

        tool_lines = "\n".join(
            f"- {t['key']}: {t['description']} "
            f"Params: {t.get('parameter_hints', '')}"
            for t in usable_tools
        )
        prompt = (
            f"Source: {item.source.value}\n"
            f"Title: {item.title}\n"
            f"Body: {item.body}\n"
            f"Repository: {repo}\n"
            f"Operator instruction: {comment}\n\n"
            f"Available tools:\n{tool_lines}\n\n"
            f"Pick the best tool and return its key as action. "
            f"If no tool matches, return action='none'.\n"
            f"Include relevant parameters in params."
        )
        schema = {
            "title": "RemoteActionPlan",
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "params": {"type": "object"},
                "reasoning": {"type": "string"},
            },
            "required": ["action", "params", "reasoning"],
        }
        try:
            completion = await self._chat_provider.complete_json(
                prompt, schema,
            )
        except Exception:
            logger.exception("Steering LLM failed: item=%s", item.id)
            return {
                "type": "steering_error",
                "message": "LLM interpretation failed.",
            }

        plan = completion.data or {}
        action = plan.get("action", "none")
        logger.info(
            "Steering plan: action=%s params=%s",
            action, plan.get("params"),
        )

        if action == "none":
            return {
                "type": "steering_skip",
                "reasoning": plan.get("reasoning", ""),
            }

        if action not in allowed:
            logger.warning(
                "Steering blocked: action=%s not in allowed=%s",
                action, allowed,
            )
            return {
                "type": "steering_error",
                "action": action,
                "message": f"Action '{action}' is not enabled. "
                f"Allowed: {', '.join(allowed)}",
            }

        connector = self._connectors[item.source]
        params = plan.get("params", {})
        try:
            result = await connector.execute_remote_action(
                action, params,
            )
        except Exception:
            logger.exception(
                "Steering action failed: action=%s item=%s",
                action, item.id,
            )
            return {
                "type": "steering_error",
                "action": action,
                "message": "Remote action failed.",
            }

        logger.info("Steering result: %s", result)
        return {
            "type": "steering_action",
            "action": action,
            "params": params,
            "result": result,
        }

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
