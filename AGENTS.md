# Repository Guide

## Scope

These instructions apply to the entire repository.

## Working Style

- Make surgical changes only.
- Prefer the simplest implementation that satisfies the current requirement.
- Do not add speculative abstractions or dormant features.
- Keep Python and TypeScript changes aligned with the existing style.

## Verification

Run the relevant checks after changes:

- `uv run --extra dev pytest`
- `uv run --extra dev ruff check src tests`
- `npm --prefix apps/web run build`

## Knowledge System Rules

- SQLite is the source of truth for stored knowledge.
- ChromaDB is only the semantic index.
- Knowledge mutations must stay centralized in `src/work_harness/services/knowledge_service.py`.
- Startup-time automatic knowledge seeding is disabled.
- Knowledge should be stored, updated, or removed only through explicit policy-approved flows.

## Webhook Rules

- Webhook delivery logging stays separate from work-item creation.
- Signature verification is required when a provider secret is configured.
- Provider-specific lifecycle events may mutate knowledge, but those rules should remain centralized in the knowledge service.

## Safety

- Do not add bulk historical sync by default.
- Any future historical import must be scoped, rate-limited, and operator-approved.
