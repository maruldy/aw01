from __future__ import annotations

import logging
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from work_harness.connectors.base import ConnectorAdapter
from work_harness.domain.models import (
    ActivityEvent,
    AnalysisRecord,
    ConnectorSource,
    KnowledgeSyncAction,
    KnowledgeSyncResult,
)
from work_harness.services.knowledge_policy import (
    build_search_query,
    build_searchable_text,
    evaluate_storeability,
)
from work_harness.services.knowledge_store import KnowledgeStore
from work_harness.services.settings_service import SettingsService

logger = logging.getLogger("work_harness.services.knowledge")


class KnowledgeService:
    def __init__(
        self,
        store: KnowledgeStore,
        settings_service: SettingsService,
    ) -> None:
        self._store = store
        self._settings_service = settings_service

    async def gather_context(
        self,
        event: ActivityEvent,
        connector: ConnectorAdapter | None,
    ) -> dict[str, Any]:
        logger.debug(
            "Gathering context: source=%s type=%s",
            event.source.value, event.event_type,
        )
        runtime_settings = await self._settings_service.get_runtime_settings_for_source(
            event.source
        )
        decision = evaluate_storeability(event, runtime_settings)
        knowledge_hits = await self._store.search_similar(
            build_search_query(event),
            source=event.source.value,
            scope_key=decision.scope_key,
            k=5,
        )
        if knowledge_hits:
            logger.info(
                "Knowledge local hit: source=%s hits=%d scope=%s",
                event.source.value, len(knowledge_hits),
                decision.scope_key,
            )
            return {
                "knowledge_mode": "local_hit",
                "knowledge_hits": knowledge_hits,
                "knowledge_scope": decision.scope_key,
            }

        if connector is None or not decision.storeable:
            logger.info(
                "Knowledge miss: source=%s scope=%s storeable=%s",
                event.source.value, decision.scope_key,
                decision.storeable,
            )
            return {
                "knowledge_mode": "miss",
                "knowledge_scope": decision.scope_key,
            }

        logger.info(
            "Knowledge remote fallback: source=%s scope=%s",
            event.source.value, decision.scope_key,
        )
        remote_context = await connector.fetch_context(event)
        return {
            "knowledge_mode": "remote_fallback",
            "knowledge_scope": decision.scope_key,
            **remote_context,
        }

    async def sync_webhook_event(
        self,
        event: ActivityEvent,
        connector: ConnectorAdapter | None,
    ) -> KnowledgeSyncResult:
        logger.info(
            "Sync webhook: source=%s type=%s",
            event.source.value, event.event_type,
        )
        runtime_settings = await self._settings_service.get_runtime_settings_for_source(
            event.source
        )
        decision = evaluate_storeability(event, runtime_settings)
        action = self._decide_sync_action(event)
        analysis_id = self._stable_analysis_id(event.source, decision.record_key)
        logger.debug(
            "Sync decision: action=%s key=%s id=%s storeable=%s",
            action.value, decision.record_key,
            analysis_id, decision.storeable,
        )

        if action == KnowledgeSyncAction.SKIP:
            return KnowledgeSyncResult(
                action=action,
                record_key=decision.record_key,
                analysis_id=analysis_id,
                scope_key=decision.scope_key,
                reason="The event is not a knowledge mutation point.",
            )

        if action == KnowledgeSyncAction.DELETE:
            await self._store.delete_analysis(analysis_id)
            return KnowledgeSyncResult(
                action=action,
                record_key=decision.record_key,
                analysis_id=analysis_id,
                scope_key=decision.scope_key,
                reason="The webhook represents a deletion or removal event.",
            )

        if not decision.storeable:
            return KnowledgeSyncResult(
                action=KnowledgeSyncAction.SKIP,
                record_key=decision.record_key,
                analysis_id=analysis_id,
                scope_key=decision.scope_key,
                reason=decision.reason,
            )

        remote_context = await connector.fetch_context(event) if connector else {}
        summary, final_summary, keywords = self._summarize(event, remote_context)
        record = AnalysisRecord(
            analysis_id=analysis_id,
            ticket_key=decision.record_key,
            source=event.source,
            scope_type=decision.scope_type,
            scope_key=decision.scope_key,
            actor=event.actor,
            canonical_url=decision.canonical_url,
            core_issue=summary,
            keywords=keywords,
            summary=summary,
            final_summary=final_summary,
            searchable_text=build_searchable_text(
                event,
                summary,
                final_summary,
                keywords,
            ),
            storeable=True,
        )
        await self._store.store_analysis(record)
        logger.info(
            "Knowledge upserted: id=%s key=%s scope=%s",
            analysis_id, decision.record_key,
            decision.scope_key,
        )
        return KnowledgeSyncResult(
            action=KnowledgeSyncAction.UPSERT,
            record_key=decision.record_key,
            analysis_id=analysis_id,
            scope_key=decision.scope_key,
            reason="The webhook matched a knowledge upsert policy.",
        )

    def _decide_sync_action(self, event: ActivityEvent) -> KnowledgeSyncAction:
        lowered = event.event_type.lower()
        if event.source == ConnectorSource.JIRA:
            if "deleted" in lowered or "removed" in lowered:
                return KnowledgeSyncAction.DELETE
            if self._is_jira_terminal(event):
                return KnowledgeSyncAction.UPSERT
            return KnowledgeSyncAction.SKIP
        if event.source == ConnectorSource.CONFLUENCE:
            if any(word in lowered for word in ("removed", "deleted", "trashed")):
                return KnowledgeSyncAction.DELETE
            if any(word in lowered for word in ("created", "updated", "published")):
                return KnowledgeSyncAction.UPSERT
            return KnowledgeSyncAction.SKIP
        if event.source == ConnectorSource.GITHUB:
            if ".closed" in lowered:
                return KnowledgeSyncAction.UPSERT
            if any(word in lowered for word in ("deleted", "removed")):
                return KnowledgeSyncAction.DELETE
            return KnowledgeSyncAction.SKIP
        if event.source == ConnectorSource.SLACK:
            slack_event = event.metadata.get("event", {})
            subtype = slack_event.get("subtype") if isinstance(slack_event, dict) else None
            if subtype in {"message_deleted", "message_retracted"}:
                return KnowledgeSyncAction.DELETE
            if subtype == "message_changed":
                return KnowledgeSyncAction.UPSERT
            if "app_mention" in lowered or "message.im" in lowered:
                return KnowledgeSyncAction.UPSERT
            return KnowledgeSyncAction.SKIP
        return KnowledgeSyncAction.SKIP

    def _is_jira_terminal(self, event: ActivityEvent) -> bool:
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        issue = metadata.get("issue", {})
        fields = issue.get("fields", {}) if isinstance(issue, dict) else {}
        status = fields.get("status") if isinstance(fields, dict) else None
        resolution = fields.get("resolution") if isinstance(fields, dict) else None
        status_name = status.get("name") if isinstance(status, dict) else None
        return bool(
            resolution
            or (
                status_name
                and status_name.lower() in {"done", "resolved", "closed"}
            )
        )

    def _summarize(
        self,
        event: ActivityEvent,
        remote_context: dict[str, Any],
    ) -> tuple[str, str, list[str]]:
        remote = remote_context.get("remote_resource", {})
        if event.source == ConnectorSource.JIRA:
            title = remote.get("summary") or event.title
            status = remote.get("status") or "done"
            return (
                f"{title} is finalized in Jira.",
                f"Terminal Jira status: {status}.",
                ["jira", "terminal_issue"],
            )
        if event.source == ConnectorSource.CONFLUENCE:
            title = remote.get("title") or event.title
            return (
                f"{title} was published or updated in Confluence.",
                "The latest document state was synced into local knowledge.",
                ["confluence", "page_update"],
            )
        if event.source == ConnectorSource.GITHUB:
            title = remote.get("title") or event.title
            return (
                f"{title} reached a terminal GitHub state.",
                "The final PR or issue outcome was synced into local knowledge.",
                ["github", "terminal_state"],
            )
        return (
            event.title,
            "A scoped Slack conversation was synced into local knowledge.",
            ["slack", "conversation"],
        )

    def _stable_analysis_id(self, source: ConnectorSource, record_key: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"{source.value}:{record_key}"))
