from __future__ import annotations

from typing import Any

import httpx

from work_harness.config import Settings
from work_harness.connectors.base import ConnectorAdapter
from work_harness.domain.models import (
    ActivityEvent,
    CapabilityStatus,
    ConnectorCapability,
    ConnectorSource,
    EventSubscription,
)


def _is_verified(capabilities: list[ConnectorCapability], key: str) -> bool:
    return any(cap.key == key and cap.status == CapabilityStatus.VERIFIED for cap in capabilities)


class JiraSelfHostedEnterpriseAdapter(ConnectorAdapter):
    source = ConnectorSource.JIRA

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def validate(self) -> dict[str, Any]:
        missing_fields = []
        if not self._settings.jira_base_url:
            missing_fields.append("JIRA_BASE_URL")
        if not self._settings.jira_api_token:
            missing_fields.append("JIRA_API_TOKEN")

        capabilities = [
            ConnectorCapability(
                key="auth",
                label="Authenticate to Jira",
                status=(
                    CapabilityStatus.MISSING_CONFIG
                    if missing_fields
                    else CapabilityStatus.UNKNOWN
                ),
                detail="Validate the Jira token against the self-hosted REST API.",
            ),
            ConnectorCapability(
                key="issue_read",
                label="Read issues",
                status=(
                    CapabilityStatus.MISSING_CONFIG
                    if missing_fields
                    else CapabilityStatus.UNKNOWN
                ),
                detail="Read issue payloads needed for event triage.",
            ),
            ConnectorCapability(
                key="issue_search",
                label="Search issues",
                status=(
                    CapabilityStatus.MISSING_CONFIG
                    if missing_fields
                    else CapabilityStatus.UNKNOWN
                ),
                detail="Run limited JQL searches for enrichment and backfill.",
            ),
        ]

        identity = None
        evidence: list[str] = []
        if not missing_fields:
            base_url = self._settings.jira_base_url.rstrip("/")
            headers = {
                "Authorization": f"Bearer {self._settings.jira_api_token}",
                "Accept": "application/json",
            }
            try:
                async with httpx.AsyncClient(
                    base_url=base_url,
                    headers=headers,
                    timeout=5.0,
                ) as client:
                    myself_response = await client.get("/rest/api/2/myself")
                    if myself_response.is_success:
                        identity = myself_response.json().get("displayName")
                        capabilities[0].status = CapabilityStatus.VERIFIED
                        capabilities[0].detail = "The Jira token authenticated successfully."
                        if identity:
                            evidence.append(f"Identity: {identity}")
                    else:
                        capabilities[0].status = CapabilityStatus.BLOCKED
                        capabilities[0].detail = (
                            "Authentication probe failed with status "
                            f"{myself_response.status_code}."
                        )

                    search_response = await client.get(
                        "/rest/api/2/search",
                        params={"maxResults": 1},
                    )
                    if search_response.is_success:
                        capabilities[1].status = CapabilityStatus.VERIFIED
                        capabilities[1].detail = "The token can read issue results."
                        capabilities[2].status = CapabilityStatus.VERIFIED
                        capabilities[2].detail = "The token can execute limited JQL search."
                    else:
                        capabilities[1].status = CapabilityStatus.BLOCKED
                        capabilities[1].detail = (
                            f"Issue read probe failed with status {search_response.status_code}."
                        )
                        capabilities[2].status = CapabilityStatus.BLOCKED
                        capabilities[2].detail = (
                            f"Issue search probe failed with status {search_response.status_code}."
                        )
            except httpx.HTTPError as exc:
                capabilities[0].status = CapabilityStatus.BLOCKED
                capabilities[0].detail = f"Authentication probe failed: {exc}"
                capabilities[1].status = CapabilityStatus.UNKNOWN
                capabilities[1].detail = (
                    "Issue read could not be confirmed because auth probe failed."
                )
                capabilities[2].status = CapabilityStatus.UNKNOWN
                capabilities[2].detail = (
                    "Issue search could not be confirmed because auth probe failed."
                )

        configured = not missing_fields and _is_verified(capabilities, "auth")
        message = (
            "Jira self-hosted is ready for read-only ingestion probes."
            if configured
            else (
                "Connect Jira self-hosted and verify read access "
                "before enabling live issue alerts."
            )
        )
        return {
            "ok": configured,
            "configured": configured,
            "source": self.source.value,
            "identity": identity,
            "missing_fields": missing_fields,
            "capabilities": [cap.model_dump(mode="json") for cap in capabilities],
            "message": message,
            "evidence": evidence,
        }

    async def poll_events(self) -> list[ActivityEvent]:
        return []

    async def handle_webhook(self, payload: dict[str, Any]) -> ActivityEvent:
        issue = payload.get("issue", {})
        fields = issue.get("fields", {})
        return ActivityEvent(
            source=self.source,
            event_type=payload.get("webhookEvent", "jira.updated"),
            title=fields.get("summary", "Jira activity"),
            body=fields.get("description") or "Jira event received.",
            external_id=str(issue.get("id", payload.get("timestamp", "jira-event"))),
            actor=(payload.get("user") or {}).get("displayName"),
            metadata=payload,
        )

    async def fetch_context(self, event: ActivityEvent) -> dict[str, Any]:
        return {
            "projects": (
                self._settings.jira_projects.split(",")
                if self._settings.jira_projects
                else []
            )
        }

    async def execute_remote_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": False,
            "source": self.source.value,
            "action": action,
            "message": "Not implemented.",
        }

    def available_subscriptions(self) -> list[EventSubscription]:
        return [
            EventSubscription(
                key="issue_created",
                label="Issue created",
                description="Create a work item when a new Jira issue appears.",
                required_capabilities=["issue_read"],
            ),
            EventSubscription(
                key="issue_updated",
                label="Issue updated",
                description="Track edits to an existing Jira issue.",
                required_capabilities=["issue_read"],
            ),
            EventSubscription(
                key="issue_transitioned",
                label="Issue transitioned",
                description="Watch status transitions that may need action.",
                required_capabilities=["issue_read"],
            ),
            EventSubscription(
                key="comment_created",
                label="Comment added",
                description="React to new comments on tracked Jira issues.",
                required_capabilities=["issue_read"],
            ),
        ]

    def classify_event(self, event: ActivityEvent) -> str | None:
        lowered = event.event_type.lower()
        if "comment" in lowered:
            return "comment_created"
        if "transition" in lowered:
            return "issue_transitioned"
        if "created" in lowered:
            return "issue_created"
        if "updated" in lowered:
            return "issue_updated"
        return None


class ConfluenceSelfHostedEnterpriseAdapter(ConnectorAdapter):
    source = ConnectorSource.CONFLUENCE

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def validate(self) -> dict[str, Any]:
        missing_fields = []
        if not self._settings.confluence_url:
            missing_fields.append("CONFLUENCE_URL")
        if not self._settings.confluence_api_token:
            missing_fields.append("CONFLUENCE_API_TOKEN")

        capabilities = [
            ConnectorCapability(
                key="auth",
                label="Authenticate to Confluence",
                status=(
                    CapabilityStatus.MISSING_CONFIG
                    if missing_fields
                    else CapabilityStatus.UNKNOWN
                ),
                detail="Validate the Confluence token against the self-hosted REST API.",
            ),
            ConnectorCapability(
                key="space_read",
                label="Read spaces",
                status=(
                    CapabilityStatus.MISSING_CONFIG
                    if missing_fields
                    else CapabilityStatus.UNKNOWN
                ),
                detail="Read configured spaces for backfill and event context.",
            ),
            ConnectorCapability(
                key="content_read",
                label="Read content",
                status=(
                    CapabilityStatus.MISSING_CONFIG
                    if missing_fields
                    else CapabilityStatus.UNKNOWN
                ),
                detail="Read Confluence pages and comments for enrichment.",
            ),
        ]

        identity = None
        evidence: list[str] = []
        if not missing_fields:
            base_url = self._settings.confluence_url.rstrip("/")
            headers = {
                "Authorization": f"Bearer {self._settings.confluence_api_token}",
                "Accept": "application/json",
            }
            try:
                async with httpx.AsyncClient(
                    base_url=base_url,
                    headers=headers,
                    timeout=5.0,
                ) as client:
                    current_user = await client.get("/rest/api/user/current")
                    if current_user.is_success:
                        identity = current_user.json().get("displayName")
                        capabilities[0].status = CapabilityStatus.VERIFIED
                        capabilities[0].detail = "The Confluence token authenticated successfully."
                        if identity:
                            evidence.append(f"Identity: {identity}")
                    else:
                        capabilities[0].status = CapabilityStatus.BLOCKED
                        capabilities[0].detail = (
                            f"Authentication probe failed with status {current_user.status_code}."
                        )

                    spaces_response = await client.get("/rest/api/space", params={"limit": 1})
                    if spaces_response.is_success:
                        capabilities[1].status = CapabilityStatus.VERIFIED
                        capabilities[1].detail = "The token can read Confluence spaces."
                    else:
                        capabilities[1].status = CapabilityStatus.BLOCKED
                        capabilities[1].detail = (
                            f"Space read probe failed with status {spaces_response.status_code}."
                        )

                    content_response = await client.get("/rest/api/content", params={"limit": 1})
                    if content_response.is_success:
                        capabilities[2].status = CapabilityStatus.VERIFIED
                        capabilities[2].detail = "The token can read Confluence content."
                    else:
                        capabilities[2].status = CapabilityStatus.BLOCKED
                        capabilities[2].detail = (
                            f"Content read probe failed with status {content_response.status_code}."
                        )
            except httpx.HTTPError as exc:
                capabilities[0].status = CapabilityStatus.BLOCKED
                capabilities[0].detail = f"Authentication probe failed: {exc}"
                capabilities[1].status = CapabilityStatus.UNKNOWN
                capabilities[1].detail = (
                    "Space read could not be confirmed because auth probe failed."
                )
                capabilities[2].status = CapabilityStatus.UNKNOWN
                capabilities[2].detail = (
                    "Content read could not be confirmed because auth probe failed."
                )

        configured = not missing_fields and _is_verified(capabilities, "auth")
        message = (
            "Confluence self-hosted is ready for read-only ingestion probes."
            if configured
            else (
                "Connect Confluence self-hosted and verify read access "
                "before enabling live content alerts."
            )
        )
        return {
            "ok": configured,
            "configured": configured,
            "source": self.source.value,
            "identity": identity,
            "missing_fields": missing_fields,
            "capabilities": [cap.model_dump(mode="json") for cap in capabilities],
            "message": message,
            "evidence": evidence,
        }

    async def poll_events(self) -> list[ActivityEvent]:
        return []

    async def handle_webhook(self, payload: dict[str, Any]) -> ActivityEvent:
        page = payload.get("page", {})
        return ActivityEvent(
            source=self.source,
            event_type=payload.get("eventType", "confluence.updated"),
            title=page.get("title", "Confluence activity"),
            body=payload.get("message", "Confluence event received."),
            external_id=str(page.get("id", payload.get("timestamp", "confluence-event"))),
            actor=(payload.get("user") or {}).get("displayName"),
            metadata=payload,
        )

    async def fetch_context(self, event: ActivityEvent) -> dict[str, Any]:
        return {
            "spaces": (
                self._settings.confluence_spaces.split(",")
                if self._settings.confluence_spaces
                else []
            )
        }

    async def execute_remote_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": False,
            "source": self.source.value,
            "action": action,
            "message": "Not implemented.",
        }

    def available_subscriptions(self) -> list[EventSubscription]:
        return [
            EventSubscription(
                key="page_created",
                label="Page created",
                description="Create work from new Confluence pages in watched spaces.",
                required_capabilities=["content_read"],
            ),
            EventSubscription(
                key="page_updated",
                label="Page updated",
                description="Review page edits that may change team guidance.",
                required_capabilities=["content_read"],
            ),
            EventSubscription(
                key="comment_created",
                label="Comment added",
                description="Surface new comments on important Confluence content.",
                required_capabilities=["content_read"],
            ),
        ]

    def classify_event(self, event: ActivityEvent) -> str | None:
        lowered = event.event_type.lower()
        if "comment" in lowered:
            return "comment_created"
        if "created" in lowered:
            return "page_created"
        if "updated" in lowered:
            return "page_updated"
        return None
