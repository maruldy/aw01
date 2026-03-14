from __future__ import annotations

from typing import Any

from work_harness.config import Settings
from work_harness.connectors.base import ConnectorAdapter
from work_harness.domain.models import ActivityEvent, ConnectorSource


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
        if not self._settings.jira_username:
            missing_fields.append("JIRA_USERNAME")

        return {
            "ok": not missing_fields,
            "configured": not missing_fields,
            "source": self.source.value,
            "missing_fields": missing_fields,
            "message": (
                "Jira self-hosted enterprise is connected."
                if not missing_fields
                else "Connect Jira self-hosted enterprise to start ingesting real issue activity."
            ),
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

        return {
            "ok": not missing_fields,
            "configured": not missing_fields,
            "source": self.source.value,
            "missing_fields": missing_fields,
            "message": (
                "Confluence self-hosted enterprise is connected."
                if not missing_fields
                else (
                    "Connect Confluence self-hosted enterprise "
                    "to enrich tickets with internal docs."
                )
            ),
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
