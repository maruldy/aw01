from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from work_harness.config import Settings
from work_harness.connectors.factory import build_connectors
from work_harness.domain.models import (
    ConnectorConfigUpdate,
    ConnectorSource,
    DecisionPayload,
    SubscriptionPreferenceUpdate,
    WebhookProvider,
)
from work_harness.graph.supervisor import SupervisorService
from work_harness.providers.openai_provider import OpenAIChatProvider
from work_harness.providers.rule_based import RuleBasedChatProvider
from work_harness.services.audit_log import AuditLog
from work_harness.services.harness import HarnessService
from work_harness.services.knowledge_service import KnowledgeService
from work_harness.services.knowledge_store import KnowledgeStore
from work_harness.services.scheduler import SchedulerService
from work_harness.services.settings_advisor import SettingsAdvisor
from work_harness.services.settings_service import SettingsService
from work_harness.services.settings_store import SettingsStore
from work_harness.services.webhook_service import WebhookReceiverService
from work_harness.services.webhook_store import WebhookStore


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
    knowledge_store = KnowledgeStore(
        app_settings.knowledge_db_path,
        app_settings.knowledge_chroma_path / app_settings.knowledge_db_path.stem,
    )
    settings_store = SettingsStore(app_settings.knowledge_db_path)
    webhook_store = WebhookStore(app_settings.knowledge_db_path)
    settings_advisor = SettingsAdvisor(
        provider if app_settings.openai_api_key else None
    )
    settings_service = SettingsService(
        app_settings,
        connectors,
        settings_store,
        settings_advisor,
    )
    knowledge_service = KnowledgeService(knowledge_store, settings_service)
    supervisor = SupervisorService(
        chat_provider=provider,
        connectors=connectors,
        knowledge_service=knowledge_service,
    )
    audit_log = AuditLog()
    webhooks = WebhookReceiverService(app_settings, webhook_store)
    harness = HarnessService(
        supervisor,
        connectors,
        audit_log,
        settings_service,
    )
    scheduler = SchedulerService()

    async def ensure_runtime(app: FastAPI) -> None:
        if getattr(app.state, "runtime_ready", False):
            return
        await knowledge_store.initialize()
        await settings_store.initialize()
        await webhook_store.initialize()
        scheduler.start()
        app.state.runtime_ready = True

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = app_settings
        app.state.harness = harness
        app.state.scheduler = scheduler
        app.state.knowledge_store = knowledge_store
        app.state.settings_service = settings_service
        app.state.webhooks = webhooks
        app.state.knowledge_service = knowledge_service
        await ensure_runtime(app)
        yield
        scheduler.stop()

    app = FastAPI(title=app_settings.app_name, lifespan=lifespan)
    app.state.settings = app_settings
    app.state.harness = harness
    app.state.scheduler = scheduler
    app.state.knowledge_store = knowledge_store
    app.state.settings_service = settings_service
    app.state.webhooks = webhooks
    app.state.knowledge_service = knowledge_service
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
        return {"ok": True, "knowledge": stats}

    @app.post("/ingress/{source}", status_code=202)
    async def ingress(source: str, request: IngressRequest) -> dict[str, Any]:
        await ensure_runtime(app)
        try:
            connector_source = ConnectorSource(source)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Unknown source") from exc
        result = await app.state.harness.ingest_event(connector_source, request.model_dump())
        return {
            "processed": result.processed,
            "subscription_key": result.subscription_key,
            "reason": result.reason,
            "work_item": (
                result.work_item.model_dump(mode="json")
                if result.work_item
                else None
            ),
            "run": (
                result.run.model_dump(mode="json")
                if result.run
                else None
            ),
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
        profiles = await app.state.settings_service.list_profiles()
        return {"profiles": [profile.model_dump(mode="json") for profile in profiles]}

    @app.post("/settings/validate/{source}")
    async def validate_connector(source: str) -> dict[str, Any]:
        await ensure_runtime(app)
        try:
            connector_source = ConnectorSource(source)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Unknown source") from exc
        profile = await app.state.settings_service.get_profile(connector_source)
        return profile.model_dump(mode="json")

    @app.post("/settings/subscriptions/{source}")
    async def update_subscriptions(
        source: str,
        payload: SubscriptionPreferenceUpdate,
    ) -> dict[str, Any]:
        await ensure_runtime(app)
        try:
            connector_source = ConnectorSource(source)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Unknown source") from exc
        profile = await app.state.settings_service.update_selected_event_keys(
            connector_source,
            payload.selected_event_keys,
        )
        return profile.model_dump(mode="json")

    @app.post("/settings/config/{source}")
    async def update_config(
        source: str,
        payload: ConnectorConfigUpdate,
    ) -> dict[str, Any]:
        await ensure_runtime(app)
        try:
            connector_source = ConnectorSource(source)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Unknown source") from exc
        profile = await app.state.settings_service.update_runtime_settings(
            connector_source,
            payload.values,
        )
        return profile.model_dump(mode="json")

    async def _receive_webhook(
        provider: WebhookProvider,
        request: Request,
    ) -> tuple[dict[str, Any], int]:
        raw_body = await request.body()
        payload = await request.json()
        verification, envelope = await app.state.webhooks.receive(
            provider,
            raw_body,
            request.headers,
            payload,
        )
        knowledge_payload = {
            "knowledge_action": "skip",
            "knowledge_reason": "Rejected or not evaluated.",
        }
        if verification.accepted:
            connector_source = ConnectorSource(provider.value)
            connector = await app.state.settings_service.get_runtime_connector(
                connector_source
            )
            event = await connector.handle_webhook(payload)
            sync_result = await app.state.knowledge_service.sync_webhook_event(
                event,
                connector,
            )
            knowledge_payload = {
                "knowledge_action": sync_result.action.value,
                "knowledge_reason": sync_result.reason,
                "knowledge_record_key": sync_result.record_key,
            }
        response_payload = {
            "accepted": verification.accepted,
            "verified": verification.verified,
            "delivery_id": envelope.delivery_id,
            "event_type": envelope.event_type,
            "status": envelope.status,
            "reason": verification.verification_reason,
            **knowledge_payload,
        }
        return response_payload, verification.status_code

    @app.post("/webhooks/github")
    async def receive_github_webhook(request: Request) -> JSONResponse:
        await ensure_runtime(app)
        payload, status_code = await _receive_webhook(WebhookProvider.GITHUB, request)
        return JSONResponse(status_code=status_code, content=payload)

    @app.post("/webhooks/slack/events")
    async def receive_slack_webhook(request: Request) -> JSONResponse:
        await ensure_runtime(app)
        raw_body = await request.body()
        payload = await request.json()
        verification, envelope = await app.state.webhooks.receive(
            WebhookProvider.SLACK,
            raw_body,
            request.headers,
            payload,
        )
        if payload.get("type") == "url_verification" and verification.accepted:
            return JSONResponse(status_code=200, content={"challenge": payload["challenge"]})
        knowledge_payload = {
            "knowledge_action": "skip",
            "knowledge_reason": "Rejected or not evaluated.",
        }
        if verification.accepted:
            connector = await app.state.settings_service.get_runtime_connector(
                ConnectorSource.SLACK
            )
            event = await connector.handle_webhook(payload)
            sync_result = await app.state.knowledge_service.sync_webhook_event(
                event,
                connector,
            )
            knowledge_payload = {
                "knowledge_action": sync_result.action.value,
                "knowledge_reason": sync_result.reason,
                "knowledge_record_key": sync_result.record_key,
            }
        response_payload = {
            "accepted": verification.accepted,
            "verified": verification.verified,
            "delivery_id": envelope.delivery_id,
            "event_type": envelope.event_type,
            "status": envelope.status,
            "reason": verification.verification_reason,
            **knowledge_payload,
        }
        return JSONResponse(status_code=verification.status_code, content=response_payload)

    @app.post("/webhooks/jira")
    async def receive_jira_webhook(request: Request) -> JSONResponse:
        await ensure_runtime(app)
        payload, status_code = await _receive_webhook(WebhookProvider.JIRA, request)
        return JSONResponse(status_code=status_code, content=payload)

    @app.post("/webhooks/confluence")
    async def receive_confluence_webhook(request: Request) -> JSONResponse:
        await ensure_runtime(app)
        payload, status_code = await _receive_webhook(WebhookProvider.CONFLUENCE, request)
        return JSONResponse(status_code=status_code, content=payload)

    @app.get("/webhooks/deliveries")
    async def list_webhook_deliveries(
        provider: str | None = None,
        verified: bool | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        await ensure_runtime(app)
        webhook_provider = None
        if provider is not None:
            try:
                webhook_provider = WebhookProvider(provider)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail="Unknown webhook provider") from exc
        items = await app.state.webhooks.list_deliveries(
            provider=webhook_provider,
            verified=verified,
            limit=max(1, min(limit, 100)),
        )
        return {"items": [item.model_dump(mode="json") for item in items]}

    return app
