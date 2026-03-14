from pathlib import Path

import pytest

from work_harness.domain.models import AnalysisRecord, ConnectorSource
from work_harness.services.knowledge_store import KnowledgeStore


@pytest.mark.asyncio
async def test_knowledge_store_searches_with_scope_filter_and_vector_index(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", tmp_path / "chroma")
    await store.initialize()

    await store.store_analysis(
        AnalysisRecord(
            ticket_key="OPS-1",
            source=ConnectorSource.JIRA,
            scope_type="project",
            scope_key="OPS",
            core_issue="Operations incident",
            summary="Investigate the database issue",
            final_summary="Prepare an operations follow-up",
            searchable_text="replication lag saturation incident",
        )
    )
    await store.store_analysis(
        AnalysisRecord(
            ticket_key="APP-1",
            source=ConnectorSource.JIRA,
            scope_type="project",
            scope_key="APP",
            core_issue="Application regression",
            summary="UI alignment problem",
            final_summary="Ask the frontend owner to follow up",
            searchable_text="layout glitch ui spacing",
        )
    )

    results = await store.search_similar(
        "replication lag",
        source="jira",
        scope_key="OPS",
        k=5,
    )

    assert results
    assert results[0]["ticket_key"] == "OPS-1"
    assert all(result["scope_key"] == "OPS" for result in results)


@pytest.mark.asyncio
async def test_knowledge_store_hybrid_search_returns_empty_when_scope_is_blocked(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db", tmp_path / "chroma")
    await store.initialize()

    await store.store_analysis(
        AnalysisRecord(
            ticket_key="OPS-2",
            source=ConnectorSource.JIRA,
            scope_type="project",
            scope_key="OPS",
            core_issue="Database pressure",
            summary="High write amplification",
            final_summary="Investigate saturation",
            searchable_text="replication lag saturation incident",
        )
    )

    results = await store.search_similar(
        "replication lag",
        source="jira",
        scope_key="APP",
        k=5,
    )

    assert results == []
