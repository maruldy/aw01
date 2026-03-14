from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from work_harness.config import Settings
from work_harness.connectors.factory import build_connectors
from work_harness.domain.models import ConnectorProfile, ConnectorSource, DecisionPayload
from work_harness.graph.supervisor import SupervisorService
from work_harness.providers.openai_provider import OpenAIChatProvider
from work_harness.providers.rule_based import RuleBasedChatProvider
from work_harness.services.audit_log import AuditLog
from work_harness.services.bootstrap import BootstrapService
from work_harness.services.harness import HarnessService
from work_harness.services.knowledge_store import KnowledgeStore
from work_harness.services.scheduler import SchedulerService


class IngressRequest(BaseModel):
    event_type: str
    title: str
    body: str
    external_id: str
    actor: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkItemsResponse(BaseModel):
    items: list[dict[str, Any]]


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings()
    connectors = build_connectors(app_settings)
    provider = (
        OpenAIChatProvider(app_settings)
        if app_settings.openai_api_key
        else RuleBasedChatProvider()
    )
    supervisor = SupervisorService(chat_provider=provider, connectors=connectors)
    knowledge_store = KnowledgeStore(app_settings.knowledge_db_path)
    audit_log = AuditLog()
    harness = HarnessService(supervisor, connectors, knowledge_store, audit_log)
    bootstrap = BootstrapService(knowledge_store)
    scheduler = SchedulerService(app_settings, bootstrap)

    async def ensure_runtime(app: FastAPI) -> None:
        if getattr(app.state, "runtime_ready", False):
            return
        await knowledge_store.initialize()
        scheduler.start()
        app.state.runtime_ready = True

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = app_settings
        app.state.harness = harness
        app.state.bootstrap = bootstrap
        app.state.scheduler = scheduler
        app.state.knowledge_store = knowledge_store
        await ensure_runtime(app)
        if app_settings.auto_bootstrap:
            await bootstrap.trigger()
        yield
        scheduler.stop()

    app = FastAPI(title=app_settings.app_name, lifespan=lifespan)
    app.state.settings = app_settings
    app.state.harness = harness
    app.state.bootstrap = bootstrap
    app.state.scheduler = scheduler
    app.state.knowledge_store = knowledge_store
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        await ensure_runtime(app)
        stats = await app.state.knowledge_store.get_stats()
        bootstrap_status = await app.state.bootstrap.status()
        return {"ok": True, "knowledge": stats, "bootstrap": bootstrap_status}

    @app.post("/ingress/{source}", status_code=202)
    async def ingress(source: str, request: IngressRequest) -> dict[str, Any]:
        await ensure_runtime(app)
        try:
            connector_source = ConnectorSource(source)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Unknown source") from exc
        result = await app.state.harness.ingest_event(connector_source, request.model_dump())
        return {
            "work_item": result.work_item.model_dump(mode="json"),
            "run": result.run.model_dump(mode="json"),
        }

    @app.get("/work-items")
    async def list_work_items() -> WorkItemsResponse:
        await ensure_runtime(app)
        items = await app.state.harness.list_work_items()
        return WorkItemsResponse(items=[item.model_dump(mode="json") for item in items])

    @app.get("/work-items/{item_id}")
    async def get_work_item(item_id: str) -> dict[str, Any]:
        await ensure_runtime(app)
        item = await app.state.harness.get_work_item(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Work item not found")
        return item.model_dump(mode="json")

    @app.post("/work-items/{item_id}/decision")
    async def decide(item_id: str, payload: DecisionPayload) -> dict[str, Any]:
        await ensure_runtime(app)
        try:
            item = await app.state.harness.decide(item_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Work item not found") from exc
        return item.model_dump(mode="json")

    @app.get("/runs/{thread_id}/stream")
    async def stream_run(thread_id: str):
        await ensure_runtime(app)
        return EventSourceResponse(app.state.harness.stream_events(thread_id))

    @app.get("/runs/{thread_id}")
    async def get_run(thread_id: str) -> dict[str, Any]:
        await ensure_runtime(app)
        run = await app.state.harness.get_run(thread_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return run.model_dump(mode="json")

    @app.post("/bootstrap/trigger")
    async def trigger_bootstrap() -> dict[str, Any]:
        await ensure_runtime(app)
        return await app.state.bootstrap.trigger()

    @app.get("/bootstrap/status")
    async def bootstrap_status() -> dict[str, Any]:
        await ensure_runtime(app)
        return await app.state.bootstrap.status()

    @app.get("/knowledge/stats")
    async def knowledge_stats() -> dict[str, Any]:
        await ensure_runtime(app)
        return await app.state.knowledge_store.get_stats()

    @app.get("/knowledge/recent")
    async def knowledge_recent() -> dict[str, Any]:
        await ensure_runtime(app)
        return {"items": await app.state.knowledge_store.get_recent()}

    @app.get("/scheduler/jobs")
    async def scheduler_jobs() -> dict[str, Any]:
        await ensure_runtime(app)
        return {"jobs": app.state.scheduler.list_jobs()}

    @app.get("/audit/recent")
    async def audit_recent() -> dict[str, Any]:
        await ensure_runtime(app)
        return {"items": await app.state.harness.get_recent_audit()}

    @app.get("/settings/profiles")
    async def settings_profiles() -> dict[str, Any]:
        await ensure_runtime(app)
        profiles = []
        for source, _connector in connectors.items():
            mode = (
                "self_hosted_enterprise"
                if source in {ConnectorSource.JIRA, ConnectorSource.CONFLUENCE}
                else "cloud_enterprise"
            )
            validation = await connectors[source].validate()
            profiles.append(
                ConnectorProfile(
                    name=source.value,
                    source=source,
                    mode=mode,
                    settings={},
                    configured=bool(validation["configured"]),
                    missing_fields=list(validation["missing_fields"]),
                    message=str(validation["message"]),
                ).model_dump(mode="json")
            )
        return {"profiles": profiles}

    @app.post("/settings/validate/{source}")
    async def validate_connector(source: str) -> dict[str, Any]:
        await ensure_runtime(app)
        try:
            connector_source = ConnectorSource(source)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Unknown source") from exc
        connector = connectors[connector_source]
        return await connector.validate()

    return app
