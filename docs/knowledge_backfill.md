# Knowledge Backfill Flow

## Purpose

The backfill flow exists to avoid an empty knowledge base on first deployment. Instead of waiting for new live activity, the system should scan recent enterprise data, normalize it, summarize it, and store it so later agent runs can use similar past cases as context.

## Current implementation

The current code path lives in [backfill.py](../src/work_harness/services/backfill.py). It is intentionally a safe dry run:

1. Mark backfill as `running`
2. Create one synthetic `AnalysisRecord`
3. Store it in SQLite through `KnowledgeStore`
4. Mark backfill as `completed`

This proves the orchestration, scheduler registration, and storage path end to end without requiring live enterprise credentials during local development.

## Current operating policy

Backfill is not the default knowledge strategy.

The implemented runtime now prefers:

1. local scoped retrieval from SQLite + ChromaDB
2. scoped single-resource remote fallback on a local miss
3. storeability checks before persistence

That keeps the system safe for internal services while still letting the harness accumulate useful knowledge over time.

## Target production flow

In production, the intended backfill pipeline is:

1. Validate connector credentials for Jira, Confluence, Slack, and GitHub
2. Pull historical data for a bounded time range such as the last 3-6 months
3. Normalize vendor-specific payloads into internal activity records
4. Run lightweight LLM analysis to extract issue summaries, keywords, owners, and likely next actions
5. Persist structured records into SQLite and searchable summaries into the vector layer
6. Record checkpoints so the job can resume after interruptions

## Workflow diagram

```mermaid
flowchart TD
    A["Backfill triggered"] --> B["Validate connector credentials"]
    B --> C["Fetch historical Jira/Confluence/Slack/GitHub data"]
    C --> D["Normalize into internal activity records"]
    D --> E["Run lightweight analysis"]
    E --> F["Store structured rows in SQLite"]
    E --> G["Store summaries for similarity search"]
    F --> H["Update checkpoint + progress"]
    G --> H
    H --> I{"More batches?"}
    I -->|Yes| C
    I -->|No| J["Backfill completed"]
```

## Why this matters in the work harness

- The inbox can explain similar past incidents instead of starting from zero.
- Supervisor routing gets better context for proposals and prioritization.
- Human decisions become reusable organizational memory rather than one-off actions.
- Daily delta scans can stay small because the cold-start bulk load already populated the baseline.
