from pathlib import Path

import pytest

from work_harness.config import Settings
from work_harness.connectors.base import ConnectorAdapter
from work_harness.domain.models import (
    ActivityEvent,
    AnalysisRecord,
    ConnectorSource,
    EventSubscription,
)
from work_harness.services.knowledge_service import KnowledgeService
from work_harness.services.knowledge_store import KnowledgeStore


class FakeSettingsService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def get_runtime_settings_for_source(self, source: ConnectorSource) -> Settings:
        return self._settings


class FakeConnector(ConnectorAdapter):
    source = ConnectorSource.JIRA

    def __init__(self) -> None:
        self.fetch_calls = 0

    async def validate(self) -> dict[str, object]:
        return {}

    async def poll_events(self) -> list[ActivityEvent]:
        return []

    async def handle_webhook(self, payload: dict[str, object]) -> ActivityEvent:
        raise NotImplementedError

    async def fetch_context(self, event: ActivityEvent) -> dict[str, object]:
        self.fetch_calls += 1
        return {"remote": True, "issue_key": event.metadata["issue"]["key"]}

    async def execute_remote_action(
        self,
        action: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return {}

    def available_subscriptions(self) -> list[EventSubscription]:
        return []

    def classify_event(self, event: ActivityEvent) -> str | None:
        return None


@pytest.mark.asyncio
async def test_knowledge_service_prefers_local_hits_before_remote_fetch(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", tmp_path / "chroma")
    await store.initialize()
    await store.store_analysis(
        AnalysisRecord(
            ticket_key="OPS-3",
            source=ConnectorSource.JIRA,
            scope_type="project",
            scope_key="OPS",
            core_issue="Database incident",
            summary="Primary database replication lag",
            final_summary="Review the prior database response",
            searchable_text="replication lag failover incident",
        )
    )
    service = KnowledgeService(
        store=store,
        settings_service=FakeSettingsService(Settings(jira_projects="OPS")),
    )
    connector = FakeConnector()
    event = ActivityEvent(
        source=ConnectorSource.JIRA,
        event_type="jira:issue_updated",
        title="OPS-10 replication lag",
        body="Primary database replication lag",
        external_id="10010",
        metadata={"issue": {"key": "OPS-10"}},
    )

    context = await service.gather_context(event, connector)

    assert context["knowledge_mode"] == "local_hit"
    assert context["knowledge_hits"]
    assert connector.fetch_calls == 0


@pytest.mark.asyncio
async def test_knowledge_service_falls_back_to_remote_context_on_miss(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", tmp_path / "chroma")
    await store.initialize()
    service = KnowledgeService(
        store=store,
        settings_service=FakeSettingsService(Settings(jira_projects="OPS")),
    )
    connector = FakeConnector()
    event = ActivityEvent(
        source=ConnectorSource.JIRA,
        event_type="jira:issue_updated",
        title="OPS-11 unknown issue",
        body="No local hit yet",
        external_id="10011",
        metadata={"issue": {"key": "OPS-11"}},
    )

    context = await service.gather_context(event, connector)

    assert context["knowledge_mode"] == "remote_fallback"
    assert context["remote"] is True
    assert connector.fetch_calls == 1


@pytest.mark.asyncio
async def test_knowledge_service_does_not_fetch_remote_context_for_blocked_scope(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", tmp_path / "chroma")
    await store.initialize()
    service = KnowledgeService(
        store=store,
        settings_service=FakeSettingsService(Settings(jira_projects="OPS")),
    )
    connector = FakeConnector()
    event = ActivityEvent(
        source=ConnectorSource.JIRA,
        event_type="jira:issue_updated",
        title="APP-11 unknown issue",
        body="Out of scope",
        external_id="10011",
        metadata={"issue": {"key": "APP-11"}},
    )

    context = await service.gather_context(event, connector)

    assert context["knowledge_mode"] == "miss"
    assert connector.fetch_calls == 0
