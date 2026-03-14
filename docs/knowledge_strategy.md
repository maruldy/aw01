# Knowledge Strategy

## Decision

The harness should not default to bulk historical backfill against Jira, Confluence, Slack, or GitHub.

Instead, the default knowledge flow is:

1. Check local knowledge first.
2. If the local hit is weak, fetch remote context on demand.
3. Decide whether the fetched data is allowed to be stored.
4. Store only sanitized summaries and scoped metadata.

This reduces the risk of sudden high request volume against internal systems and keeps the knowledge base aligned with the operator's actual working scope.

## Storage Roles

### SQLite

SQLite is the source of truth.

- Stores the canonical record metadata
- Stores scope information such as Jira project, Confluence space, Slack channel, GitHub repository
- Stores sanitized summaries, keywords, timestamps, and decision context
- Enforces filtering by source, scope, recency, and policy

### ChromaDB

ChromaDB is the semantic index.

- Stores embedding-ready text derived from sanitized summaries
- Stores only minimal metadata needed for retrieval
- Never acts as the canonical record store
- Must not bypass SQLite policy checks

## Retrieval Policy

Retrieval should be hybrid:

1. Build a scoped query from the incoming event or operator action.
2. Filter candidate records in SQLite by allowed scope and recency.
3. Run semantic similarity search in ChromaDB over the same allowed scope.
4. Merge and rerank the results.
5. Hydrate final result details from SQLite.

If the merged result is weak, the harness may fetch remote context on demand.

## Storeability Gate

Remote data is not stored automatically just because it was fetched.

The harness should only store data when the source is in the operator's allowed working scope.

Examples:

- Jira: issue project key is in the allowed project list
- Confluence: page space key is in the allowed space list
- Slack: message channel is in the allowed channel list, or it is a direct conversation that the operator is part of
- GitHub: repository matches the explicitly allowed repository list

If data is useful for the current run but fails the storeability gate, it can be used as transient context only and must not be persisted.

## Data Minimization

The harness should prefer storing:

- sanitized summary
- extracted keywords
- source identifier
- scope identifier
- timestamps
- URLs or stable references

The harness should avoid storing full raw bodies by default, especially for Slack and Confluence content.

## Backfill Policy

Historical backfill is not implemented by default.

If backfill is implemented later, it must include:

- explicit operator approval
- strict scope allowlists
- a bounded time window
- low concurrency
- per-provider rate limiting
- request budgets
- checkpoint and resume
- safe stop controls

## Why This Fits the Harness

- safer for internal systems
- better aligned with operator-driven scope
- avoids building a large low-value corpus
- supports semantic recall without giving up strict policy control
