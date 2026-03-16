from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
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


class GitHubConnectStartRequest(BaseModel):
    frontend_origin: str
    next_path: str = "/settings"


logger = logging.getLogger("work_harness.api")


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
    from work_harness.repositories.sqlite import (
        SqliteRunRepository,
        SqliteWorkItemRepository,
    )

    work_item_repo = SqliteWorkItemRepository(app_settings.knowledge_db_path)
    run_repo = SqliteRunRepository(app_settings.knowledge_db_path)
    audit_log = AuditLog()
    webhooks = WebhookReceiverService(app_settings, webhook_store)
    harness = HarnessService(
        supervisor,
        connectors,
        audit_log,
        settings_service,
        chat_provider=provider,
        work_items=work_item_repo,
        runs=run_repo,
    )
    scheduler = SchedulerService()

    async def ensure_runtime(app: FastAPI) -> None:
        if getattr(app.state, "runtime_ready", False):
            return
        logger.info("Initializing runtime: stores + scheduler")
        await knowledge_store.initialize()
        await settings_store.initialize()
        await webhook_store.initialize()
        await harness.initialize()
        scheduler.start()
        app.state.runtime_ready = True
        logger.info("Runtime initialization complete")

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
        logger.info(
            "POST /ingress/%s type=%s id=%s",
            source, request.event_type, request.external_id,
        )
        try:
            connector_source = ConnectorSource(source)
        except ValueError as exc:
            logger.warning("Unknown ingress source: %s", source)
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
        logger.info("POST /work-items/%s/decision decision=%s", item_id, payload.decision.value)
        try:
            item = await app.state.harness.decide(item_id, payload)
        except KeyError as exc:
            logger.warning("Decision target not found: %s", item_id)
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
        profile = await app.state.settings_service.get_profile(
            connector_source, force_validate=True,
        )
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

    @app.get("/settings/actions/{source}")
    async def get_allowed_actions(source: str) -> dict[str, Any]:
        await ensure_runtime(app)
        try:
            connector_source = ConnectorSource(source)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Unknown source") from exc
        available = await app.state.settings_service.get_available_tools(
            connector_source,
        )
        allowed = await app.state.settings_service.get_allowed_actions(
            connector_source,
        )
        profile = await app.state.settings_service.get_profile(connector_source)
        return {
            "source": source,
            "detected_scopes": profile.detected_scopes,
            "available": available,
            "allowed": allowed,
        }

    @app.post("/settings/actions/{source}")
    async def update_allowed_actions(
        source: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        await ensure_runtime(app)
        try:
            connector_source = ConnectorSource(source)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Unknown source") from exc
        actions = payload.get("allowed", [])
        saved = await app.state.settings_service.set_allowed_actions(
            connector_source, actions,
        )
        available = await app.state.settings_service.get_available_tools(
            connector_source,
        )
        return {
            "source": source,
            "available": available,
            "allowed": saved,
        }

    @app.post("/settings/github/connect/start")
    async def start_github_connect(
        payload: GitHubConnectStartRequest,
    ) -> dict[str, str]:
        await ensure_runtime(app)
        try:
            authorization_url = await app.state.settings_service.start_github_connection(
                payload.frontend_origin,
                payload.next_path,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"authorization_url": authorization_url}

    @app.get("/settings/github/callback")
    async def complete_github_connect(code: str, state: str) -> RedirectResponse:
        await ensure_runtime(app)
        try:
            redirect_url = await app.state.settings_service.complete_github_connection(
                code,
                state,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse(redirect_url)

    @app.get("/settings/github/repositories")
    async def list_github_repositories() -> dict[str, Any]:
        await ensure_runtime(app)
        try:
            repositories = await app.state.settings_service.list_github_repositories()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"repositories": repositories}

    @app.get("/settings/github/recommended-repos")
    async def list_github_recommended_repos() -> dict[str, Any]:
        await ensure_runtime(app)
        try:
            repos = await app.state.settings_service.list_github_recommended_repos()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"repositories": repos}

    async def _receive_webhook(
        provider: WebhookProvider,
        request: Request,
    ) -> tuple[dict[str, Any], int]:
        import json
        from urllib.parse import parse_qs

        logger.info("Webhook received: provider=%s", provider.value)
        raw_body = await request.body()
        payload: dict[str, Any] = {}
        if raw_body:
            content_type = request.headers.get("content-type", "")
            if "json" in content_type:
                try:
                    payload = json.loads(raw_body)
                except Exception:
                    logger.warning("JSON parse failed: provider=%s", provider.value)
            elif "form" in content_type:
                parsed = parse_qs(raw_body.decode())
                form_payload = parsed.get("payload", [None])[0]
                if form_payload:
                    try:
                        payload = json.loads(form_payload)
                    except Exception:
                        logger.warning("Form payload parse failed: provider=%s", provider.value)
            else:
                try:
                    payload = json.loads(raw_body)
                except Exception:
                    logger.warning("Body parse failed: provider=%s", provider.value)
        verification, envelope = await app.state.webhooks.receive(
            provider,
            raw_body,
            request.headers,
            payload,
        )
        logger.info(
            "Webhook verified: provider=%s accepted=%s verified=%s delivery_id=%s event_type=%s",
            provider.value, verification.accepted, verification.verified,
            envelope.delivery_id, envelope.event_type,
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
            try:
                ingress_result = await app.state.harness.ingest_event(
                    connector_source, payload,
                )
                knowledge_payload["work_item_id"] = (
                    ingress_result.work_item.id
                    if ingress_result.work_item
                    else None
                )
                knowledge_payload["processed"] = ingress_result.processed
            except Exception:
                logger.exception(
                    "Webhook work item creation failed: %s",
                    provider.value,
                )
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

    # Serve frontend static files in production
    import pathlib

    static_dir = pathlib.Path(
        os.environ.get("STATIC_DIR", "/app/static")
    )
    if static_dir.is_dir():
        from fastapi.staticfiles import StaticFiles
        from starlette.responses import FileResponse

        index_html = static_dir / "index.html"

        app.mount(
            "/assets",
            StaticFiles(directory=str(static_dir / "assets")),
            name="static-assets",
        )

        @app.get("/")
        async def serve_index():
            return FileResponse(index_html)

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            file_path = static_dir / full_path
            if file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(index_html)

    return app
