# LangGraph Work Harness

Event-driven AI work harness for enterprise operations. The system is built around a LangGraph supervisor that turns inbound Jira, Confluence, Slack, and GitHub activity into operator-facing work items instead of chat replies.

## What is included

- FastAPI backend with a LangGraph supervisor graph
- Self-hosted Jira and Confluence adapters, plus Slack Enterprise Grid and GitHub Enterprise Cloud adapters
- Safety harness with tool allowlist and approval-aware action policy
- SQLite-backed knowledge store and bootstrap/scheduler services
- React + Vite frontend with inbox, runs, knowledge, and settings views
- Local development helpers: `.env.example`, `Makefile`, Docker, and GitHub Actions CI

## Local development

```bash
cp .env.example .env
make setup
make setup-web
make run-api
make run-web
```

The frontend runs on `http://localhost:5173` and the backend on `http://localhost:8000`.

## Architecture notes

- Jira and Confluence are assumed to be self-hosted enterprise deployments.
- Slack and GitHub are assumed to be cloud enterprise products.
- MCP is not required by the core runtime. SaaS and self-hosted system access goes through typed connector adapters; local side effects go through an allowlisted CLI registry.
- The UI is push-first: agents create work items, and the operator responds with `accept`, `reject`, `advise`, or `defer`.

Bootstrap details are documented in [knowledge_bootstrap.md](/Users/maruldy/dev/workspace/aw01/docs/knowledge_bootstrap.md).
