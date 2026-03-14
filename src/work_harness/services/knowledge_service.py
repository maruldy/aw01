from __future__ import annotations

from typing import Any

from work_harness.connectors.base import ConnectorAdapter
from work_harness.domain.models import ActivityEvent, AnalysisRecord, ExecutionRun, WorkItem
from work_harness.services.knowledge_policy import (
    build_search_query,
    build_searchable_text,
    evaluate_storeability,
)
from work_harness.services.knowledge_store import KnowledgeStore
from work_harness.services.settings_service import SettingsService


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
        runtime_settings = await self._settings_service.get_runtime_settings_for_source(
            event.source
        )
        decision = evaluate_storeability(event, runtime_settings)
        query = build_search_query(event)
        knowledge_hits = await self._store.search_similar(
            query,
            source=event.source.value,
            scope_key=decision.scope_key,
            k=5,
        )
        if knowledge_hits:
            return {
                "knowledge_mode": "local_hit",
                "knowledge_hits": knowledge_hits,
                "knowledge_scope": decision.scope_key,
            }

        if connector is None or not decision.storeable:
            return {
                "knowledge_mode": "miss",
                "knowledge_scope": decision.scope_key,
            }

        remote_context = await connector.fetch_context(event)
        return {
            "knowledge_mode": "remote_fallback",
            "knowledge_scope": decision.scope_key,
            **remote_context,
        }

    async def build_analysis_record(
        self,
        event: ActivityEvent,
        work_item: WorkItem,
        run: ExecutionRun,
    ) -> AnalysisRecord | None:
        runtime_settings = await self._settings_service.get_runtime_settings_for_source(
            event.source
        )
        decision = evaluate_storeability(event, runtime_settings)
        if not decision.storeable:
            return None

        keywords = [event.source.value, work_item.proposal.recommended_agent]
        return AnalysisRecord(
            ticket_key=decision.record_key,
            source=event.source,
            scope_type=decision.scope_type,
            scope_key=decision.scope_key,
            actor=event.actor,
            canonical_url=decision.canonical_url,
            core_issue=work_item.proposal.summary,
            keywords=keywords,
            summary=work_item.proposal.summary,
            final_summary=work_item.proposal.suggested_action,
            searchable_text=build_searchable_text(
                event,
                work_item.proposal.summary,
                work_item.proposal.suggested_action,
                keywords,
            ),
            session_id=run.thread_id,
            storeable=True,
        )

    async def store_analysis(self, record: AnalysisRecord) -> str:
        return await self._store.store_analysis(record)
