from __future__ import annotations

from work_harness.config import Settings
from work_harness.connectors.base import ConnectorAdapter
from work_harness.domain.models import ActivityEvent, ConnectorSource


class GitHubEnterpriseCloudAdapter(ConnectorAdapter):
    source = ConnectorSource.GITHUB

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def validate(self) -> dict[str, object]:
        missing_fields = []
        if not self._settings.github_token:
            missing_fields.append("GITHUB_TOKEN")
        if not self._settings.github_repository:
            missing_fields.append("GITHUB_REPOSITORY")
        return {
            "ok": not missing_fields,
            "configured": not missing_fields,
            "source": self.source.value,
            "missing_fields": missing_fields,
            "message": (
                "GitHub Enterprise Cloud is connected."
                if not missing_fields
                else (
                    "Connect GitHub Enterprise Cloud to turn "
                    "reviews and PR requests into managed work."
                )
            ),
        }

    async def poll_events(self) -> list[ActivityEvent]:
        return []

    async def handle_webhook(self, payload: dict[str, object]) -> ActivityEvent:
        action = str(payload.get("action", "github.event"))
        pull_request = (
            payload.get("pull_request", {})
            if isinstance(payload.get("pull_request"), dict)
            else {}
        )
        repository = (
            payload.get("repository", {})
            if isinstance(payload.get("repository"), dict)
            else {}
        )
        title = pull_request.get("title") or repository.get("full_name") or "GitHub activity"
        body = pull_request.get("body") or f"GitHub action: {action}"
        sender = payload.get("sender", {}) if isinstance(payload.get("sender"), dict) else {}
        return ActivityEvent(
            source=self.source,
            event_type=f"github.{action}",
            title=str(title),
            body=str(body),
            external_id=str(pull_request.get("id", payload.get("delivery", "github-event"))),
            actor=str(sender.get("login")) if sender.get("login") else None,
            metadata=payload,
        )

    async def fetch_context(self, event: ActivityEvent) -> dict[str, object]:
        return {"repository": self._settings.github_repository}

    async def execute_remote_action(
        self,
        action: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return {
            "ok": False,
            "source": self.source.value,
            "action": action,
            "message": "Not implemented.",
        }
